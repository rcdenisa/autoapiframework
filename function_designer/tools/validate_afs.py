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
#
# USAGE:
#   python validate_afs.py <path/to/file.afs> [<path/to/another.afs> ...]
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
#     - MR-Init: an 'init' runnable is expected
#     - MR-Terminate: a 'terminate' runnable is expected
#     - MR-NameUnique: Data interface names must be unique
#     - MR-ParamUnique: Parameter names must be unique

import sys
import traceback
from pathlib import Path
from typing import List

import yaml
from pydantic import ValidationError

# Ensure tools/ directory is on the path when called from anywhere
sys.path.insert(0, str(Path(__file__).parent))
from afs_model import FunctionSpecificationFile, FunctionSpecificationContent


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
    else:
        run_types = {e.runType.value for e in spec.scheduling}

        # MR-Init: an init runnable is expected
        if "init" not in run_types:
            errors.append("[MR-Init] No 'init' runnable found in scheduling.")

        # MR-Terminate: a terminate runnable is expected
        if "terminate" not in run_types:
            errors.append("[MR-Terminate] No 'terminate' runnable found in scheduling.")

    return errors


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
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: python {Path(__file__).name} <file.afs> [<file2.afs> ...]")
        return 1

    paths = [Path(p) for p in sys.argv[1:]]
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

    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
