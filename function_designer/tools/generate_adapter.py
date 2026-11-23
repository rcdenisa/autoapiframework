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
# generate_adapter.py  =  Code Generator 1 (executable: AutoAPIFunctionDesigner_CodeGen_1)
#
# PURPOSE:
#   Reads an .afs file, validates it and generates the Function API
#   (interface contract) with the Jinja2 templates in templates/api*.jinja2:
#
#     .afs (YAML spec)  ->  Python (validate + parse)  ->  Jinja2  ->  <name>_api.h / .rs
#
#   Only the "api" part of the complete generated tree belongs to Code Generator 1:
#
#     generated/
#       cpp/
#         common/autoapiframework_enums.h
#         speed_hazard_detection/
#           api/         speed_hazard_detection_api.h     <- Code Generator 1 (this script)
#           adapter/     speed_hazard_detection_fad.h/.cpp <- Code Generator 2 (not here)
#           middleware/  speed_hazard_detection_mw.h/.cpp  <- Code Generator 3 (not here)
#       c/ and rust/ use the same layout (files: _api.h and _api.rs).
#
# EXPECTATIONS:
#   - Only <function_name>/api/<function_name>_api.<ext> and common/ are written.
#   - The api header includes the shared enums file with a relative path, so
#     the generated files compile without extra include directories.
#   - The script validates the .afs before generating (fail fast).
#   - Exit code 0 on success, 1 on a failed validation/generation, 2 on a usage error.
#
# USAGE:
#   Default output folder (if --output-dir is not given): "generated" in the function_designer
#   project folder, otherwise in the current directory.
#
#   python generate_adapter.py <path/to/file.afs> [--language cpp|c|rust]
#                              [--output-dir <dir>] [--enums-dir <dir>] [--skip-validation]
#   python generate_adapter.py ../examples/speed_hazard_detection.afs
#   python generate_adapter.py ../examples/speed_hazard_detection.afs --language rust --output-dir ./generated
import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))
from afs_model import FunctionSpecificationFile, Direction
from afs_common import (EXIT_FAILED, EXIT_OK, EXIT_USAGE, VERSION, HelpFormatter,
                        configure_console, exe_dir, parse_args, resolve_afs_path)
import validate_afs


# ---------------------------------------------------------------------------
# Type mapping: meta model dataType string → C++ type
# ---------------------------------------------------------------------------

_CPP_TYPE_MAP = {
    "float":   "float",
    "double":  "double",
    "uint8":   "std::uint8_t",
    "uint16":  "std::uint16_t",
    "uint32":  "std::uint32_t",
    "uint64":  "std::uint64_t",
    "int8":    "std::int8_t",
    "int16":   "std::int16_t",
    "int32":   "std::int32_t",
    "int64":   "std::int64_t",
    "boolean": "bool",
    "bool":    "bool",
    "string":  "const char*",
}

# C type map (no std:: namespace, uses stdint.h types)
_C_TYPE_MAP = {
    "float":   "float",
    "double":  "double",
    "uint8":   "uint8_t",
    "uint16":  "uint16_t",
    "uint32":  "uint32_t",
    "uint64":  "uint64_t",
    "int8":    "int8_t",
    "int16":   "int16_t",
    "int32":   "int32_t",
    "int64":   "int64_t",
    "boolean": "bool",
    "bool":    "bool",
    "string":  "const char*",
}


def _cpp_type(meta_type: str) -> str:
    """Convert a meta model dataType string to a C++ type."""
    return _CPP_TYPE_MAP.get(meta_type.lower(), meta_type)


def _c_type(meta_type: str) -> str:
    """Convert a meta model dataType string to a C type."""
    return _C_TYPE_MAP.get(meta_type.lower(), meta_type)


def _cpp_identifier(vss_name: str) -> str:
    """
    Convert a VSS-style hierarchical name to a valid C++ identifier.
    Example: Vehicle.Speed  →  Vehicle_Speed
    """
    return vss_name.replace(".", "_")


def _cpp_default_value(data_type: str) -> str:
    """
    Return the typed C++ default value for a given data type.
    Matches Thomas P. style: 0.0F for float, 0U for uint32, false for bool.
    Used for private member variable initialization.
    """
    dt = data_type.lower()
    if dt == "float":
        return "0.0F"
    if dt == "double":
        return "0.0"
    if dt in ("boolean", "bool"):
        return "false"
    if "uint" in dt:
        return "0U"
    if "int" in dt:
        return "0"
    return "0"


def _cpp_suffix(value: object, data_type: str) -> str:
    """
    Convert a Python value to a typed C++ literal.
    Matches Thomas P. style: 10.0F, 3000U, false, true.
    Used for static constexpr parameter defaults.
    """
    dt = data_type.lower()
    if dt in ("boolean", "bool"):
        return "true" if value else "false"
    if isinstance(value, bool):
        return "true" if value else "false"
    if dt == "float":
        s = str(float(value))
        s = s if "." in s else s + ".0"
        return s + "F"
    if dt == "double":
        s = str(float(value))
        return s if "." in s else s + ".0"
    if isinstance(value, int) and "uint" in dt:
        return str(value) + "U"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        s = str(value)
        s = s if "." in s else s + ".0"
        return s + "F"
    return str(value)


def _cpp_literal(value: object, data_type: str) -> str:
    """Alias for _cpp_suffix — kept for backward compatibility."""
    return _cpp_suffix(value, data_type)


def _runnable_method(function_name: str) -> str:
    """
    Extract just the method part from a qualified runnable name.
    Example: SpeedHazardDetection.Init  →  Init
             SpeedHazardDetection.Step  →  Step
    """
    parts = function_name.split(".")
    return parts[-1] if len(parts) > 1 else function_name


def _to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case. E.g. SpeedHazardDetection -> speed_hazard_detection."""
    import re
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


# ---------------------------------------------------------------------------
# Rust type mapping and filters
# ---------------------------------------------------------------------------

_RUST_TYPE_MAP = {
    "float":   "f32",
    "double":  "f64",
    "uint8":   "u8",
    "uint16":  "u16",
    "uint32":  "u32",
    "uint64":  "u64",
    "int8":    "i8",
    "int16":   "i16",
    "int32":   "i32",
    "int64":   "i64",
    "boolean": "bool",
    "bool":    "bool",
    "string":  "&'static str",
}


def _rust_type(meta_type: str) -> str:
    """Convert a meta model dataType string to a Rust type."""
    return _RUST_TYPE_MAP.get(meta_type.lower(), meta_type)


def _rust_identifier(vss_name: str) -> str:
    """
    Convert a VSS-style hierarchical name to a Rust snake_case identifier.
    Example: Vehicle.Speed -> vehicle_speed
    """
    return vss_name.replace(".", "_").lower()


def _rust_literal(value: object, data_type: str) -> str:
    """Convert a Python value to a Rust literal appropriate for data_type."""
    dt = data_type.lower()
    if dt in ("boolean", "bool"):
        return "true" if value else "false"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        rust_type = _rust_type(dt)
        s = str(value)
        s = s if "." in s else s + ".0"
        return f"{s}_{rust_type}"   # e.g. 10.0_f32
    if isinstance(value, int):
        rust_type = _rust_type(dt)
        return f"{value}_{rust_type}"  # e.g. 3000_u32
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def _rust_method(function_name: str) -> str:
    """
    Extract method name from qualified runnable name and convert to snake_case.
    Example: SpeedHazardDetection.Step -> step
    """
    parts = function_name.split(".")
    method = parts[-1] if len(parts) > 1 else function_name
    return method.lower()


# ---------------------------------------------------------------------------
# Jinja2 environment setup
# ---------------------------------------------------------------------------

def _build_jinja_env() -> Environment:
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )
    # Register custom filters — C++
    env.filters["cpp_type"]          = _cpp_type
    env.filters["cpp_identifier"]    = _cpp_identifier
    env.filters["cpp_literal"]       = _cpp_literal
    env.filters["cpp_suffix"]        = _cpp_suffix
    env.filters["cpp_default_value"] = _cpp_default_value
    env.filters["runnable_method"]   = _runnable_method
    # Register custom filters — C
    env.filters["c_type"]            = _c_type
    # Register custom filters — Rust
    env.filters["rust_type"]         = _rust_type
    env.filters["rust_identifier"]   = _rust_identifier
    env.filters["rust_literal"]      = _rust_literal
    env.filters["rust_method"]       = _rust_method
    # Generic utility filters
    env.filters["ljust"]             = lambda s, width: str(s).ljust(width)
    return env


def _check_and_generate_enums(
    output_dir: Path,
    meta_model_name: str,
    meta_model_version: str,
    language: str,
    env: "Environment",
) -> tuple:
    """
    Ensures the shared autoapiframework_enums file exists and is up to date.

    Logic:
      - If the file does not exist → generate it.
      - If the file exists but was generated for a different meta model version → regenerate.
      - If the file exists and the version matches → skip (no overwrite).

    Returns (path, action) where action is one of:
      'created'    — file did not exist, was generated
      'updated'    — file existed but was outdated, was regenerated
      'up-to-date' — file exists and matches current meta model version
    """
    if language in ("cpp",):
        filename      = "autoapiframework_enums.h"
        template_name = "autoapiframework_enums.hpp.jinja2"
    elif language == "c":
        filename      = "autoapiframework_enums.h"
        template_name = "autoapiframework_enums_c.h.jinja2"
    elif language == "rust":
        filename      = "autoapiframework_enums.rs"
        template_name = "autoapiframework_enums.rs.jinja2"
    else:
        return None, "skipped"

    enums_path     = output_dir / filename
    version_marker = f"{meta_model_name} {meta_model_version}"

    # Check if file exists and is already up to date
    if enums_path.exists():
        first_line = enums_path.read_text(encoding="utf-8").split("\n")[0]
        if version_marker in first_line:
            return enums_path, "up-to-date"
        action = "updated"
    else:
        action = "created"

    # Generate enums file from template
    context = {
        "meta_model_name":    meta_model_name,
        "meta_model_version": meta_model_version,
    }
    template = env.get_template(template_name)
    rendered = template.render(**context)
    enums_path.write_text(rendered, encoding="utf-8")

    return enums_path, action


# language -> (template, file extension of the api file)
_LANGUAGES = {
    "cpp":  ("api.hpp.jinja2",   "h"),
    "c":    ("api_c.h.jinja2",   "h"),
    "rust": ("api.rs.jinja2",    "rs"),
}


def _relative_include(target: Path, from_dir: Path) -> str:
    """Path of `target` relative to `from_dir`, with forward slashes (for #include)."""
    try:
        return os.path.relpath(target, from_dir).replace(os.sep, "/")
    except ValueError:  # e.g. different drives on Windows
        return target.name


def _compute_cpp_alignments(inputs, outputs, errors, params):
    """
    Compute column widths for aligned C++ declarations matching Thomas P. style.
    Returns (mem_type_col, mem_name_col, param_type_col, param_name_col).
    """
    # Private member alignment — collect all (type, full_m_name) pairs
    all_members = []
    for d in inputs:
        all_members.append((_cpp_type(d.dataType), f"m_{_cpp_identifier(d.name)}"))
        if d.runtimeCompanion and d.runtimeCompanion.qualityCode:
            all_members.append(("DataQuality", f"m_{_cpp_identifier(d.name)}_Qualifier"))
    for d in outputs:
        all_members.append((_cpp_type(d.dataType), f"m_{_cpp_identifier(d.name)}"))
        if d.runtimeCompanion and d.runtimeCompanion.qualityCode:
            all_members.append(("DataQuality", f"m_{_cpp_identifier(d.name)}_Qualifier"))
    for e in errors:
        all_members.append((_cpp_type(e.dataType), f"m_{_cpp_identifier(e.name)}"))

    mem_type_col = max((len(t) for t, _ in all_members), default=5) + 1
    mem_name_col = max((len(n) for _, n in all_members), default=8) + 4

    # Parameter alignment — collect all (type, full_k_name) pairs
    all_param_entries = []
    for p in params:
        all_param_entries.append((_cpp_type(p.dataType), f"k{_cpp_identifier(p.name)}"))

    param_type_col = max((len(t) for t, _ in all_param_entries), default=5) + 1
    param_name_col = max((len(n) for _, n in all_param_entries), default=8) + 3

    return mem_type_col, mem_name_col, param_type_col, param_name_col


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def generate(afs_path: Path, output_dir: Path, language: str = "cpp",
             enums_dir: Path = None) -> list:
    """
    Code Generator 1: generates the Function API (interface contract) from an .afs file.
    language:  "cpp" and "c" generate <name>_api.h, "rust" generates <name>_api.rs
    output_dir: root of the generated tree, files go to
               <output_dir>/<language>/<name>/api/ (see the layout in the module header).
    enums_dir: directory for the shared enums file. Defaults to <output_dir>/<language>/common.
    Returns a list of generated file paths.
    Raises SystemExit on any error.
    """
    # --- Load YAML ---
    try:
        raw = yaml.safe_load(afs_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        print(f"ERROR: Could not load {afs_path}: {exc}", file=sys.stderr)
        raise SystemExit(1)

    # --- Validate with Pydantic ---
    try:
        spec_file = FunctionSpecificationFile.model_validate(raw)
    except ValidationError as exc:
        print(f"ERROR: {afs_path} failed validation ({exc.error_count()} error(s)):", file=sys.stderr)
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err["loc"])
            print(f"  {loc}: {err['msg']}", file=sys.stderr)
        raise SystemExit(1)

    spec = spec_file.functionSpecification

    # --- Prepare template context ---
    inputs  = [d for d in spec.dataInterfaces if d.direction == Direction.input]
    outputs = [d for d in spec.dataInterfaces if d.direction == Direction.output]
    params  = spec.parameters
    errors  = spec.errors or []

    # A parameter constant needs a value: an empty (null) defaultValue is accepted by the
    # validation (MR-005: unknown stays null) but no value may be invented for the code.
    no_default = [p.name for p in params if p.defaultValue is None]
    if no_default:
        print(f"ERROR: {afs_path.name}: cannot generate code, defaultValue is empty (null) for "
              f"parameter(s): {', '.join(no_default)}", file=sys.stderr)
        raise SystemExit(1)
    # --- Select template, output folder and file name by language ---
    # Code Generator 1 only generates the Function API (interface contract):
    #   <output_dir>/<language>/common/autoapiframework_enums.<ext>      (shared by all functions)
    #   <output_dir>/<language>/<function_name>/api/<function_name>_api.<ext>
    # The adapter/ (Code Generator 2) and middleware/ (Code Generator 3) folders are not created here.
    base_name = _to_snake_case(spec.name)

    if language not in _LANGUAGES:
        print(f"ERROR: Unknown language '{language}'. Use cpp, c, or rust.", file=sys.stderr)
        raise SystemExit(1)
    template_name, api_extension = _LANGUAGES[language]
    output_filename = f"{base_name}_api.{api_extension}"

    env = _build_jinja_env()
    language_root = output_dir / language
    api_dir = language_root / base_name / "api"
    api_dir.mkdir(parents=True, exist_ok=True)

    # enums_dir defaults to <output_dir>/<language>/common if not specified
    resolved_enums_dir = enums_dir if enums_dir else language_root / "common"
    resolved_enums_dir.mkdir(parents=True, exist_ok=True)

    # --- Step 1: Ensure shared enums file is present and up to date ---
    enums_path, enums_action = _check_and_generate_enums(
        resolved_enums_dir,
        spec.metaModelRef.name,
        spec.metaModelRef.version,
        language,
        env,
    )
    if enums_path:
        if enums_action == "created":
            print(f"Created enums : {enums_path}")
        elif enums_action == "updated":
            print(f"Updated enums : {enums_path}  (meta model version changed)")
        else:
            print(f"Enums OK      : {enums_path}  (up to date)")

    # Include path of the enums file as seen from the api header (e.g. ../../common/autoapiframework_enums.h)
    enums_include = _relative_include(enums_path, api_dir) if enums_path else "autoapiframework_enums.h"

    # Compute C++ alignment widths (only relevant for cpp template)
    mem_type_col, mem_name_col, param_type_col, param_name_col = \
        _compute_cpp_alignments(inputs, outputs, errors, params)

    # Unique tunable values for parameter comment
    param_tunable_str = ", ".join(sorted(set(str(p.tunable).lower() for p in params))) if params else ""

    context = {
        "spec":             spec,
        "inputs":           inputs,
        "outputs":          outputs,
        "params":           params,
        "errors":           errors,
        "filename":         output_filename,
        "source_file":      afs_path.name,
        "language":         language,
        "enums_include":    enums_include,
        # C++ alignment widths
        "mem_type_col":     mem_type_col,
        "mem_name_col":     mem_name_col,
        "param_type_col":   param_type_col,
        "param_name_col":   param_name_col,
        "param_tunable_str": param_tunable_str,
    }
    try:
        template = env.get_template(template_name)
        rendered = template.render(**context)
    except Exception as exc:
        print(f"ERROR: Template '{template_name}' rendering failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

    output_path = api_dir / output_filename
    output_path.write_text(rendered, encoding="utf-8")
    return [output_path]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

_PROG = "AutoAPIFunctionDesigner_CodeGen_1"

_DESCRIPTION = """\
Code Generator 1: generates the Function API (interface contract) in C++, C or
Rust from an AutoAPI function specification file (.afs). The file is fully
validated first (structure, types, enums and semantic rules); nothing is
written if it is invalid.

The adapter/ (Function Adapter) and middleware/ (Middleware Abstraction) parts
of the generated tree belong to Code Generator 2 and 3 and are not created here.
"""

_EPILOG = """\
generated files (<out> = --output-dir, default: the "generated" folder of the
function_designer project, or of the current directory if that is not found):
  <out>/cpp/common/autoapiframework_enums.h
  <out>/cpp/<function_name>/api/<function_name>_api.h
  <out>/c/common/autoapiframework_enums.h
  <out>/c/<function_name>/api/<function_name>_api.h
  <out>/rust/common/autoapiframework_enums.rs
  <out>/rust/<function_name>/api/<function_name>_api.rs

(<function_name> is the function name in snake_case, e.g. speed_hazard_detection.)
The shared enums file is created if missing and regenerated only when the
meta model version changed.

examples:
  AutoAPIFunctionDesigner_CodeGen_1 speed_hazard_detection.afs
  AutoAPIFunctionDesigner_CodeGen_1 speed_hazard_detection.afs --language rust --output-dir out
  AutoAPIFunctionDesigner_CodeGen_1 f.afs --output-dir out --enums-dir shared/include

A file that is not found at the given path is also looked up next to the
executable.

exit codes:
  0  code generated
  1  validation or generation failed
  2  usage error (wrong arguments, file not found)
"""


def _is_project_root(folder: Path) -> bool:
    """True for the function_designer project folder (its CMakeLists.txt declares the project)."""
    cmake = folder / "CMakeLists.txt"
    try:
        return cmake.is_file() and "project(function_designer" in cmake.read_text(
            encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return False


def default_output_dir(afs_path: Path) -> Path:
    """
    Default root of the generated tree when no output folder was chosen:
    a "generated" folder in the function_designer project folder.

    The project folder is searched upwards from the .afs file first, then from the
    location of this tool (the executable is built inside the project, e.g.
    function_designer/build/<preset>/bin). If it cannot be found, the "generated"
    folder is created in the current working directory.
    It is never created next to the .afs file.
    """
    for start in (afs_path.parent, exe_dir()):
        for folder in (start, *start.parents):
            if _is_project_root(folder):
                return folder / "generated"
    return Path.cwd() / "generated"

def main(argv: Optional[List[str]] = None) -> int:
    configure_console()
    parser = argparse.ArgumentParser(
        prog=_PROG, description=_DESCRIPTION, epilog=_EPILOG,
        formatter_class=HelpFormatter,
    )
    parser.add_argument(
        "afs_file",
        type=Path,
        metavar="file.afs",
        help="Path to the .afs function specification file.",
    )
    parser.add_argument(
        "--language",
        choices=["cpp", "c", "rust"],
        default="cpp",
        help="Target language: cpp (_api.h), c (_api.h), rust (_api.rs). Default: cpp.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Root of the generated tree (<language>/<function_name>/api/...). Defaults to the \"generated\" folder of the function_designer project (current directory if the project is not found).",
    )
    parser.add_argument(
        "--enums-dir",
        type=Path,
        default=None,
        help=(
            "Directory for the shared autoapiframework_enums file. "
            "Should be a fixed framework include directory shared across all generated functions. "
            "Defaults to <output-dir>/<language>/common."
        ),
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Do not run the full validation (schema + semantic rules) before generating.",
    )
    parser.add_argument("--version", action="version", version=f"{_PROG} {VERSION}")
    args, exit_code = parse_args(parser, argv)
    if exit_code is not None:
        return exit_code

    afs_path: Path = resolve_afs_path(args.afs_file).resolve()
    if not afs_path.is_file():
        print(f"ERROR: File not found: {afs_path}", file=sys.stderr)
        return EXIT_USAGE

    # Full validation (schema + semantic rules) before any code is generated.
    if not args.skip_validation:
        if not validate_afs.validate_file(afs_path):
            print("\nGeneration aborted: the specification is not valid.", file=sys.stderr)
            return EXIT_FAILED
        print()

    output_dir: Path = args.output_dir.resolve() if args.output_dir else default_output_dir(afs_path)
    enums_dir:  Path = args.enums_dir.resolve()  if args.enums_dir  else None

    print(f"Generating {args.language.upper()} code for: {afs_path.name}")
    try:
        generated = generate(afs_path, output_dir, language=args.language, enums_dir=enums_dir)
    except SystemExit as exc:  # generate() reports its errors on stderr
        return EXIT_FAILED if exc.code in (None, 0) else int(exc.code)
    for path in generated:
        print(f"Generated: {path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
