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
| `pydantic` | 2.11.4 | Schema validation and parsing |
| `pyyaml` | 6.0.2 | YAML loading |
| `jinja2` | 3.1.6 | C++ code generation templates |
