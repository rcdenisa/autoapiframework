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
# generate_adapter.py
#
# PURPOSE:
#   Reads a validated .afs file and generates a C++ adapter header using
#   the Jinja2 template in templates/adapter.hpp.jinja2.
#   This is the proof-of-concept for the AutoAPI auto code generation workflow:
#
#     .afs (YAML spec)  →  Python (validate + parse)  →  Jinja2  →  C++ header
#
# EXPECTATIONS:
#   - The generated header contains Inputs, Outputs, Parameters structs.
#   - The generated header contains an IAdapter interface with one virtual
#     method per scheduling runnable.
#   - The generated file is placed next to the .afs file by default, or
#     in the directory specified with --output-dir.
#   - The script validates the .afs before generating (fail fast).
#   - Exit code 0 on success, 1 on any error.
#
# USAGE:
#   python generate_adapter.py <path/to/file.afs> [--language cpp|rust] [--output-dir <dir>]
#   python generate_adapter.py ../examples/speed_hazard_detection.afs
#   python generate_adapter.py ../examples/speed_hazard_detection.afs --language rust
#   python generate_adapter.py ../examples/speed_hazard_detection.afs --language cpp --output-dir ./generated
#
# WHAT GETS GENERATED:
#   C++ (--language cpp):
#     <FunctionName>_adapter.hpp
#       - namespace <FunctionName>
#       - struct Inputs / Outputs / Parameters
#       - DefaultParameters() constexpr factory
#       - class IAdapter with pure virtual methods per runnable
#
#   Rust (--language rust):
#     <function_name>_adapter.rs
#       - pub struct Inputs / Outputs / Parameters
#       - impl Default for Parameters
#       - pub trait Adapter with methods per runnable

import argparse
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))
from afs_model import FunctionSpecificationFile, Direction


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
    return env


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def generate(afs_path: Path, output_dir: Path, language: str = "cpp") -> list:
    """
    Validates and generates adapter file(s) from an .afs file.
    language: "cpp" generates .h + .cpp, "c" generates .h + .c, "rust" generates .rs
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

    # --- Select templates and output filenames by language ---
    base_name = _to_snake_case(spec.name)

    if language == "cpp":
        templates_and_files = [
            ("adapter.hpp.jinja2",  f"{spec.name}.h"),
            ("adapter.cpp.jinja2",  f"{spec.name}.cpp"),
        ]
    elif language == "c":
        templates_and_files = [
            ("adapter_c.h.jinja2",  f"{spec.name}.h"),
            ("adapter_c.c.jinja2",  f"{spec.name}.c"),
        ]
    elif language == "rust":
        templates_and_files = [
            ("adapter.rs.jinja2",   f"{base_name}.rs"),
        ]
    else:
        print(f"ERROR: Unknown language '{language}'. Use cpp, c, or rust.", file=sys.stderr)
        raise SystemExit(1)

    env = _build_jinja_env()
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    for template_name, output_filename in templates_and_files:
        context = {
            "spec":        spec,
            "inputs":      inputs,
            "outputs":     outputs,
            "params":      params,
            "errors":      errors,
            "filename":    output_filename,
            "source_file": afs_path.name,
            "language":    language,
        }
        try:
            template = env.get_template(template_name)
            rendered = template.render(**context)
        except Exception as exc:
            print(f"ERROR: Template '{template_name}' rendering failed: {exc}", file=sys.stderr)
            raise SystemExit(1)

        output_path = output_dir / output_filename
        output_path.write_text(rendered, encoding="utf-8")
        generated.append(output_path)

    return generated


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an adapter file from an AutoAPI .afs function specification."
    )
    parser.add_argument(
        "afs_file",
        type=Path,
        help="Path to the .afs function specification file.",
    )
    parser.add_argument(
        "--language",
        choices=["cpp", "c", "rust"],
        default="cpp",
        help="Target language: cpp (.h + .cpp), c (.h + .c), rust (.rs). Default: cpp.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for the generated files. Defaults to the directory of the .afs file.",
    )
    args = parser.parse_args()

    afs_path: Path = args.afs_file.resolve()
    if not afs_path.exists():
        print(f"ERROR: File not found: {afs_path}", file=sys.stderr)
        return 1

    output_dir: Path = args.output_dir.resolve() if args.output_dir else afs_path.parent

    print(f"Generating {args.language.upper()} adapter for: {afs_path.name}")
    generated = generate(afs_path, output_dir, language=args.language)
    for path in generated:
        print(f"Generated: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
