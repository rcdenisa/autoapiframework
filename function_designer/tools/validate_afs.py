# *******************************************************************************
# Copyright (c) 2026 ZF Friedrichshafen AG
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
#
# validate_afs.py
#
# PURPOSE:
#   Validates one or more .afs files against the AutoAPI meta model v0.4.1.
#   Uses Pydantic models from afs_model.py for structural and type validation,
#   plus additional semantic checks that go beyond pure schema conformance.
#
# EXPECTATIONS:
#   - A clean .afs produces a structured summary with no errors.
#   - A non-conformant .afs produces clear, field-level error messages
#     pointing to exactly what is wrong and where.
#   - Exit code 0 means all files are valid.
#   - Exit code 1 means at least one file has validation errors.
#   - Exit code 2 means a usage error (wrong arguments, file not found).
#
# USAGE:
#   AutoAPIFunctionDesigner_ValidateAFS <path/to/file.afs> [<path/to/another.afs> ...]
#   python validate_afs.py ../examples/speed_hazard_detection.afs
#
# WHAT IT CHECKS:
#   Structural (Pydantic):
#     - All mandatory fields are present
#     - Enum values match exactly (ASIL, Direction, RunType, etc.)
#     - Type correctness (float, bool, string, etc.)
#     - Supervision.type required when supervision.required == True
#     - cycleTimeMs required when runType == cyclic
#
#   Semantic (custom rules):
#     - MR-FuSa: if FuSa == True, ASIL must be specified
#     - MR-Schedule: at least one scheduling entry must exist
#   Advisory (shown, never blocking):
#     - MR-Init: no 'init' runnable (optional - a function may have none)
#     - MR-Terminate: no 'terminate' runnable (optional - a function may have none)
#     - MR-NameUnique: Data interface names must be unique
#     - MR-ParamUnique: Parameter names must be unique

import argparse
import sys
import traceback
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, ValidationError

# Ensure tools/ directory is on the path when called from anywhere
sys.path.insert(0, str(Path(__file__).parent))
from afs_model import FunctionSpecificationFile, FunctionSpecificationContent
from afs_common import (EXIT_FAILED, EXIT_OK, EXIT_USAGE, VERSION, HelpFormatter,
                        configure_console, parse_args, resolve_afs_path)


# ---------------------------------------------------------------------------
# ANSI colours (disabled on non-TTY environments like CI logs)
# ---------------------------------------------------------------------------

def _colour(code: str, text: str) -> str:
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text

RED    = lambda t: _colour("31", t)
GREEN  = lambda t: _colour("32", t)
YELLOW = lambda t: _colour("33", t)
BOLD   = lambda t: _colour("1",  t)
CYAN   = lambda t: _colour("36", t)

SEP  = "-" * 60
OK   = "[OK]"
FAIL = "[FAIL]"


# ---------------------------------------------------------------------------
# Semantic checks (beyond Pydantic schema)
# ---------------------------------------------------------------------------

def _semantic_checks(spec: FunctionSpecificationContent) -> List[str]:
    """
    Returns a list of semantic violation messages.
    An empty list means the spec passes all semantic rules.
    """
    errors: List[str] = []

    # MR-FuSa: safety-relevant interfaces must declare an ASIL level
    for di in spec.dataInterfaces:
        if di.FuSa and di.asil is None:
            errors.append(
                f"[MR-FuSa] dataInterface '{di.name}': FuSa=True but ASIL is not specified."
            )

    # MR-NameUnique: Data interface names must be unique
    data_names = [di.name for di in spec.dataInterfaces]
    seen: set = set()
    for n in data_names:
        if n in seen:
            errors.append(f"[MR-NameUnique] dataInterface name '{n}' is duplicated.")
        seen.add(n)

    # MR-ParamUnique: Parameter names must be unique
    param_names = [p.name for p in spec.parameters]
    seen = set()
    for n in param_names:
        if n in seen:
            errors.append(f"[MR-ParamUnique] parameter name '{n}' is duplicated.")
        seen.add(n)

    # MR-Schedule: at least one scheduling entry must exist
    if not spec.scheduling:
        errors.append("[MR-Schedule] No scheduling entries found. At least one runnable is required.")

    return errors


def _advisories(spec: FunctionSpecificationContent) -> List[str]:
    """
    Returns advisory messages: things worth a look that do NOT make the file invalid
    and never block validation or code generation.
    """
    notes: List[str] = []
    run_types = {e.runType.value for e in spec.scheduling}

    # MR-Init / MR-Terminate: not mandatory. A function without init/terminate simply has none.
    if spec.scheduling and "init" not in run_types:
        notes.append("[MR-Init] No 'init' runnable in scheduling (optional).")
    if spec.scheduling and "terminate" not in run_types:
        notes.append("[MR-Terminate] No 'terminate' runnable in scheduling (optional).")
    return notes


def _print_advisories(notes: List[str]) -> None:
    if notes:
        print(YELLOW(f"  Advisory: {len(notes)} hint(s), not blocking:"))
        for msg in notes:
            print(f"    - {msg}")


def _find_empty_mandatory(obj, path: str = "") -> List[str]:
    """
    Returns the paths of mandatory properties whose value is null/empty.
    Such properties are accepted (the key is present, the value is unknown yet,
    see the NULL RULE in afs_model.py) but are worth telling the user about.
    """
    found: List[str] = []
    if isinstance(obj, BaseModel):
        for name, field in type(obj).model_fields.items():
            value = getattr(obj, name)
            sub = f"{path}.{name}" if path else name
            if value is None and field.is_required():
                found.append(sub)
            else:
                found.extend(_find_empty_mandatory(value, sub))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(_find_empty_mandatory(item, f"{path}[{i}]"))
    return found


# ---------------------------------------------------------------------------
# Validate a single file
# ---------------------------------------------------------------------------

def validate_file(path: Path) -> bool:
    """
    Validates a single .afs file.
    Returns True if valid, False if any errors were found.
    """
    print(f"\n{BOLD(SEP)}")
    print(f"{BOLD('File:')} {CYAN(str(path))}")

    # --- Load YAML ---
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(RED(f"  [YAML ERROR] Failed to parse YAML:\n  {exc}"))
        return False
    except OSError as exc:
        print(RED(f"  [FILE ERROR] Cannot read file: {exc}"))
        return False

    # --- Structural validation via Pydantic ---
    try:
        spec_file = FunctionSpecificationFile.model_validate(raw)
    except ValidationError as exc:
        print(RED(f"  [SCHEMA ERRORS] {exc.error_count()} structural error(s) found:\n"))
        for err in exc.errors():
            location = " -> ".join(str(loc) for loc in err["loc"])
            print(f"  {RED(FAIL)} {YELLOW(location)}")
            print(f"      {err['msg']}")
        return False

    spec = spec_file.functionSpecification

    # --- Semantic checks ---
    semantic_errors = _semantic_checks(spec)

    if semantic_errors:
        print(RED(f"  [SEMANTIC ERRORS] {len(semantic_errors)} semantic rule violation(s):\n"))
        for msg in semantic_errors:
            print(f"  {RED(FAIL)} {msg}")
        _print_advisories(_advisories(spec))
        return False

    # --- Summary on success ---
    inputs  = [d for d in spec.dataInterfaces if d.direction.value == "input"]
    outputs = [d for d in spec.dataInterfaces if d.direction.value == "output"]

    print(GREEN(f"  {OK} Valid"))
    print(f"  Function   : {BOLD(spec.name)}  v{spec.version}")
    print(f"  Meta model : {spec.metaModelRef.name}  v{spec.metaModelRef.version}")
    print(f"  Inputs     : {len(inputs)}")
    print(f"  Outputs    : {len(outputs)}")
    print(f"  Parameters : {len(spec.parameters)}")
    print(f"  Runnables  : {len(spec.scheduling)}")
    if spec.errors:
        print(f"  Errors     : {len(spec.errors)} (candidate interface)")

    # Empty mandatory properties are accepted, but reported as a note.
    empty = _find_empty_mandatory(spec, "functionSpecification")
    if empty:
        print(YELLOW(f"  Note: {len(empty)} mandatory propert{'y is' if len(empty) == 1 else 'ies are'} "
                     "empty (null) - accepted, interpreted as 'not yet defined':"))
        for p in empty[:15]:
            print(f"    - {p}")
        if len(empty) > 15:
            print(f"    ... and {len(empty) - 15} more")
    _print_advisories(_advisories(spec))
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_PROG = "AutoAPIFunctionDesigner_ValidateAFS"

_DESCRIPTION = """\
Validates AutoAPI function specification files (.afs) against the meta model
(structure, types, enums and semantic rules). Nothing is written.
"""

_EPILOG = """\
examples:
  AutoAPIFunctionDesigner_ValidateAFS speed_hazard_detection.afs
  AutoAPIFunctionDesigner_ValidateAFS a.afs b.afs c.afs

A file that is not found at the given path is also looked up next to the
executable.

exit codes:
  0  all files are valid
  1  at least one file is invalid
  2  usage error (wrong arguments, file not found)
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG, description=_DESCRIPTION, epilog=_EPILOG,
        formatter_class=HelpFormatter,
    )
    parser.add_argument("afs_files", type=Path, nargs="+", metavar="file.afs",
                        help="One or more function specification files.")
    parser.add_argument("--version", action="version", version=f"{_PROG} {VERSION}")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    configure_console()
    args, exit_code = parse_args(_build_parser(), argv)
    if exit_code is not None:
        return exit_code

    paths = [resolve_afs_path(p) for p in args.afs_files]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        for p in missing:
            print(f"ERROR: File not found: {p}", file=sys.stderr)
        return EXIT_USAGE

    all_valid = True
    for p in paths:
        try:
            ok = validate_file(p)
        except Exception:
            print(RED(f"  [UNEXPECTED ERROR]"))
            traceback.print_exc()
            ok = False
        if not ok:
            all_valid = False

    print(f"\n{BOLD(SEP)}")
    if all_valid:
        print(GREEN(f"All {len(paths)} file(s) passed validation."))
    else:
        print(RED(f"Validation FAILED for one or more files."))

    return EXIT_OK if all_valid else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
