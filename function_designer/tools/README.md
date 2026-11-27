# AutoAPI Python Tooling — Proof of Concept

This folder contains Python tooling for the Eclipse Automotive API Framework.
It is a **proof of concept** and does not replace the C++ Function Designer
application. Its purpose is to explore what value a Python-based toolchain can
add to the AutoAPI workflow.

---

## Purpose

The AutoAPI workflow requires two build-time steps beyond the C++ application:

1. **Validate** — check that a `.afs` file conforms to the meta model before
   it is used as input to any code generator.
2. **Generate** — produce C++ boilerplate (adapter headers, interface structs)
   from the `.afs` specification so developers never write that by hand.

Both steps follow the rule: **Python generates, C++ executes.**
Nothing in this folder runs on the target ECU. All output is offline,
build-time artifacts.

---

## Tools

| File | Purpose |
|------|---------|
| `afs_model.py` | Pydantic v2 models mirroring meta model v0.4.1 |
| `validate_afs.py` | Validates one or more `.afs` files |
| `generate_adapter.py` | Generates a C++ adapter header from a `.afs` file |
| `templates/adapter.hpp.jinja2` | Jinja2 template for the C++ header |
| `requirements.txt` | Pinned Python dependencies |

---

## Stand-alone command-line tools (no GUI, no Python needed at run time)

Two executables, built by the normal CMake build into the same `bin/` folder as
`AutoAPIFunctionDesigner_SyntaxCheck` and `AfsFileParser`. Both take the `.afs`
file as argument and have `--help` and `--version`:

| Executable | Script | Purpose |
| --- | --- | --- |
| `AutoAPIFunctionDesigner_ValidateAFS` | `validate_afs.py` | Full validation against the meta model (schema and semantic rules). Writes nothing. |
| `AutoAPIFunctionDesigner_CodeGen_1` | `generate_adapter.py` | Code Generator 1: validates, then generates the Function API (`<name>_api.h` / `.rs`) in C++, C or Rust. |

```powershell
AutoAPIFunctionDesigner_ValidateAFS speed_hazard_detection.afs [other.afs ...]
AutoAPIFunctionDesigner_CodeGen_1   speed_hazard_detection.afs --language cpp --output-dir .\out
```

`CodeGen_1` options: `--language cpp|c|rust` (default `cpp`), `--output-dir`
(default: the `generated` folder of the `function_designer` project; the current directory if the project is not found), `--enums-dir`,
`--skip-validation`. By default it runs the full validation first and writes
nothing if the file is invalid.

It generates only the Function API. Adapter and middleware belong to Code
Generator 2 and 3:

```
generated/
  cpp/
    common/autoapiframework_enums.h
    speed_hazard_detection/
      api/speed_hazard_detection_api.h          <- Code Generator 1
      adapter/    (..._fad.h/.cpp)              <- Code Generator 2, not generated here
      middleware/ (..._mw.h/.cpp)               <- Code Generator 3, not generated here
  c/ and rust/ use the same layout (_api.h / _api.rs)
```

See `CODE_GENERATOR_1.md` for details.

Exit codes (both tools): `0` success, `1` validation/generation failed, `2`
usage error (bad arguments, file not found).

Like the syntax check, a file that is not found at the given path is also
looked up next to the executable, where the build copies the examples:
`AutoAPIFunctionDesigner_ValidateAFS speed_hazard_detection.afs`.

Building needs Python 3.9-3.14 (PyInstaller 6.16 does not support 3.15 yet):

```powershell
cmake --preset windows-gcc-debug
cmake --build --preset windows-gcc-debug        # builds everything, including both tools
cmake --build --preset windows-gcc-debug --target AutoAPIFunctionDesigner_CodeGen_1
.\build\windows-gcc-debug\bin\AutoAPIFunctionDesigner_CodeGen_1.exe --help
ctest --test-dir build/windows-gcc-debug -R "validate_afs_cli|codegen_1_cli"
```

CMake picks a suitable Python automatically (on Windows through the `py`
launcher). To force one, pass `-DAFD_TOOL_PYTHON=<path to python>`; to skip both
tools, pass `-DAFD_BUILD_PYTHON_TOOLS=OFF`. The first build creates a private
virtual environment in `<build>/python_tools_build` and needs internet access
for `pip`. Later builds only rerun PyInstaller when the Python sources or
templates changed. Without building, the same commands work as
`python validate_afs.py ...` and `python generate_adapter.py ...`. Python tooling for the Eclipse Automotive API Framework.
It is a **proof of concept** and does not replace the C++ Function Designer
application. Its purpose is to explore what value a Python-based toolchain can
add to the AutoAPI workflow.

---

## Purpose

The AutoAPI workflow requires two build-time steps beyond the C++ application:

1. **Validate** — check that a `.afs` file conforms to the meta model before
   it is used as input to any code generator.
2. **Generate** — produce C++ boilerplate (adapter headers, interface structs)
   from the `.afs` specification so developers never write that by hand.

Both steps follow the rule: **Python generates, C++ executes.**
Nothing in this folder runs on the target ECU. All output is offline,
build-time artifacts.

---

## Tools

| File | Purpose |
|------|---------|
| `afs_model.py` | Pydantic v2 models mirroring meta model v0.4.1 |
| `validate_afs.py` | Validates one or more `.afs` files |
| `generate_adapter.py` | Generates a C++ adapter header from a `.afs` file |
| `templates/adapter.hpp.jinja2` | Jinja2 template for the C++ header |
| `requirements.txt` | Pinned Python dependencies |

---

## Stand-alone command-line tool (no GUI, no Python needed at run time)

`afs_cli.py` is a single entry point for validation and code generation. It is
frozen into one executable, `autoapi_tool` (`.exe` on Windows), that takes the
`.afs` file as argument:

```powershell
autoapi_tool validate  speed_hazard_detection.afs [other.afs ...]
autoapi_tool generate  speed_hazard_detection.afs --language cpp --output-dir .\out
autoapi_tool speed_hazard_detection.afs            # shortcut for "validate"
```

`generate` options: `--language cpp|c|rust` (default `cpp`), `--output-dir`
(default: folder of the `.afs`), `--enums-dir`, `--skip-validation`. By default
`generate` runs the full validation (schema and semantic rules) first and
writes nothing if it fails.

Exit codes: `0` success, `1` validation/generation failed, `2` usage error
(bad arguments, file not found).

Build the executable (needs Python 3.9-3.14; PyInstaller 6.16 does not support
3.15 yet). It is part of the normal CMake build, like
`AutoAPIFunctionDesigner_SyntaxCheck`, and ends up in the same `bin/` folder:

```powershell
cmake --preset windows-gcc-debug
cmake --build --preset windows-gcc-debug                    # builds everything
cmake --build --preset windows-gcc-debug --target autoapi_tool   # only this tool
.\build\windows-gcc-debug\bin\autoapi_tool.exe --help
```

CMake picks a suitable Python automatically (on Windows through the `py`
launcher). To force one, pass `-DAFD_TOOL_PYTHON=<path to python>`; to skip the
tool, pass `-DAFD_BUILD_AUTOAPI_TOOL=OFF`. The first build creates a private
virtual environment in `<build>/autoapi_tool_build` and needs internet access
for `pip`. Later builds only rerun PyInstaller when the Python sources or
templates changed. `ctest` includes `autoapi_tool_*` tests.

Like the syntax check, a file that is not found at the given path is also
looked up next to the executable, where the build copies the examples:
`autoapi_tool validate speed_hazard_detection.afs`.

Without building, the same commands work as `python afs_cli.py ...`.

## Setup

```powershell
cd function_designer/tools
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Linux:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

### Validate a `.afs` file

```powershell
python validate_afs.py ..\examples\speed_hazard_detection.afs
```

Validate multiple files at once:
```powershell
python validate_afs.py ..\examples\speed_hazard_detection.afs `
                       ..\examples\vehicle_speed_fusion_multirate.afs `
                       ..\examples\wheel_speed_plausibility_check.afs
```

**What validation checks:**

Structural (Pydantic schema):
- All mandatory fields from meta model v0.4.1 are present
- Enum values are valid (`ASIL`, `Direction`, `RunType`, `FunctionResult`, ...)
- Type correctness (float, bool, string, etc.)
- `cycleTimeMs` is required when `runType == cyclic`
- `supervision.type` is required when `supervision.required == True`

Semantic (custom rules):
- `FuSa == True` implies `ASIL` must be specified
- `dataInterface` names must be unique
- `parameter` names must be unique
- At least one scheduling entry must exist
- An `init` runnable must be present
- A `terminate` runnable must be present

**Expected output on success:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
File: ..\examples\speed_hazard_detection.afs
  ✓ Valid
  Function   : SpeedHazardDetection  v1.0.0
  Meta model : Eclipse-autoapiframework-Metamodel  v0.4.1
  Inputs     : 2
  Outputs    : 1
  Parameters : 2
  Runnables  : 3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All 1 file(s) passed validation.
```

---

### Generate a C++ adapter header

```powershell
python generate_adapter.py ..\examples\speed_hazard_detection.afs
```

With a custom output directory:
```powershell
python generate_adapter.py ..\examples\speed_hazard_detection.afs --output-dir .\generated
```

**What gets generated:**

File: `SpeedHazardDetection_adapter.hpp`

```cpp
namespace SpeedHazardDetection {

struct Inputs {
    float Vehicle_Speed;                      ///< km/h, ASIL B
    float Vehicle_Acceleration_Longitudinal;  ///< m/s2, ASIL B
};

struct Outputs {
    bool Vehicle_Body_Lights_Hazard_Request;  ///< ASIL B
};

struct Parameters {
    float    Vehicle_Chassis_SpeedHazardForward;    // default: 10.0
    uint32_t Vehicle_Chassis_HazardRequestDurationMs; // default: 3000
};

inline constexpr Parameters DefaultParameters() { ... }

class IAdapter {
public:
    virtual void Init(void) = 0;
    virtual void Step(const Inputs& inputs, Outputs& outputs, const Parameters& params) = 0;
    virtual void Terminate(void) = 0;
};

} // namespace SpeedHazardDetection
```

---

## Expectations

This is a **proof of concept**. Before treating this as production tooling:

1. **Template coverage** — the current template covers the core interfaces
   (Data, Parameter, Scheduling). The `Error` interface (candidate status in
   meta model v0.4.1) is modelled in `afs_model.py` but not yet in the
   template.

2. **Meta model evolution** — when the meta model version changes, update
   `afs_model.py` first. The validator will immediately surface any `.afs`
   files that are non-conformant with the new version.

3. **Not a replacement** — this tooling does not replace the C++ Function
   Designer GUI. The GUI is the authoring tool. This tooling is for CI/CD
   validation and offline code generation.

4. **AUTOSAR / middleware-specific generation** — the current template
   generates a middleware-independent C++ interface. Platform-specific
   generation (SOME/IP config, AUTOSAR ports, S-CORE bindings) requires
   additional templates, not changes to the validator or the models.

---

## Adding a new template

1. Add a `.jinja2` file to `templates/`.
2. Add a new generator script (or extend `generate_adapter.py`) that:
   - Loads and validates the `.afs` (reuse `afs_model.py`)
   - Builds a context dict from the parsed spec
   - Renders the new template
   - Writes the output file
3. Register any new Jinja2 filters in `_build_jinja_env()` inside the
   generator script.

---

## Dependencies

| Package | Version | Role |
|---------|---------|------|
| `pydantic` | 2.12.5 | Schema validation and parsing |
| `pyyaml` | 6.0.3 | YAML loading |
| `jinja2` | 3.1.6 | C++ code generation templates |
