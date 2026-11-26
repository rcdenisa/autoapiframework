# AFS File Validation

**Document status:** Draft v1.0
**Last updated:** 2026-11-12
**Project:** Eclipse Automotive API Framework — Function Designer
**Source:** [AutoAPI Framework Documentation](https://tompzf.github.io/autoapiframework/function_designer/doc/standardization/standardization.html)

---

## Summary

The AFS validator checks that a Function Specification File (`.afs`) correctly
follows the AutoAPI meta model rules before any code generation takes place.
It runs two layers of checks — structural (schema conformance via Pydantic)
and semantic (meta model rules) — and reports exact field-level errors with
fix hints. A non-conformant file blocks code generation immediately.

Validation is available in the **Function Designer GUI** (Syntax check button),
from the **command line**, and as a **CMake/CTest target** for CI/CD integration.

---

## 1. Purpose

Before any code generation can happen, the Function Specification File (`.afs`)
must be verified to be correct. A specification that does not conform to the
meta model would produce incorrect or unusable generated code — or worse, code
that compiles but behaves incorrectly at runtime.

The validation step answers one question:

> **Does this `.afs` file correctly follow the AutoAPI meta model rules?**

Validation runs **before** code generation. If validation fails, generation
is stopped immediately and the developer is shown exactly what is wrong and
where to fix it.

---

## 2. Technology — Why Pydantic

The validator is implemented in Python using **Pydantic v2**.

Pydantic is a data validation library that lets you express a data schema as
Python classes with type annotations. When a YAML file is loaded through
a Pydantic model, it automatically checks every field — types, mandatory
presence, enum values, and custom rules — and raises a detailed, field-level
error if anything is wrong.

**Why Pydantic was chosen:**

| Criteria | Pydantic | Alternative (manual C++ validation) |
|---|---|---|
| Lines of code to cover full meta model | ~250 lines | ~1000+ lines |
| Error messages | Automatic, field-level | Manual string construction |
| Meta model update effort | Update one file (`afs_model.py`) | Update C++ structs + parser + validator |
| Enum validation | Automatic from Python enum definitions | Manual switch/if chains |
| Conditional rules | `@model_validator` decorators | Manual imperative code |
| Usable in CI without building the app | Yes — plain Python script | No — requires compiled binary |

The existing C++ application already performs a basic syntax check
(`validate_function.cpp`, ~29KB). Pydantic complements this with a deeper,
meta model-aware validation layer — in a fraction of the code.

**Why not AI for validation:**
Validation must be deterministic — the same file must always produce the same
result. AI models are probabilistic and cannot guarantee this. Pydantic
validation rules are explicit, auditable, and qualifiable under ISO 26262.

---

## 3. How Python Integrates with the C++ Application

The validator is a standalone Python script (`validate_afs.py`). The C++
Function Designer application calls it as an external process using `wxExecute`
— the same mechanism already used to call `vspec` (the COVESA VSS tool).

```
User clicks "Syntax check" in Function Designer (C++)
        ↓
C++ calls: python validate_afs.py <path/to/file.afs>
        ↓
Python/Pydantic validates the file
        ↓
Exit code 0 → pass, output shows summary
Exit code 1 → fail, output shows field-level errors
        ↓
C++ reads the output and displays it in a dialog
```

This means:
- The C++ application does not need to know anything about the meta model
- The meta model validation logic lives entirely in Python
- When the meta model changes, only `afs_model.py` needs to be updated — no C++ recompilation needed
- The same script runs identically in the GUI, from the command line, and in CI/CD pipelines

Pydantic and Jinja2 (used for code generation) are both Python libraries.
They are installed once via `pip install -r requirements.txt` and run entirely
offline — no internet connection, no external service, no API key required.

---

## 4. Two Layers of Checks

Validation runs two layers of checks in sequence. The first layer catches
structural problems, the second catches semantic problems.

### Layer 1 — Pre-parse (before YAML loading)

**Tab characters check (MR-Tabs)**

YAML requires spaces for indentation. Tab characters cause unreliable
parsing and must be corrected before any further validation can proceed.

```
[FAIL] File contains tab characters on line(s): 12, 34, 67
       YAML indentation must use spaces only.
       Fix tabs before further validation.
```

---

### Layer 2 — Structural (Pydantic schema)

Pydantic checks that the YAML content matches the meta model schema exactly.
These checks are automatic — no manual code needed for each rule.

| Check | Example of what it catches |
|---|---|
| Mandatory fields present | `unit:` field missing from a Data interface |
| Enum values valid | `ASIL: X` — must be `QM`, `A`, `B`, `C`, or `D` |
| Correct data types | `minUpdatePeriodMs: "fast"` — must be a number |
| `cycleTimeMs` required for cyclic | A cyclic runnable with no cycle time defined |
| `supervision.type` required | `supervision.required: true` but no type specified |

Example output:
```
[SCHEMA ERRORS] 1 structural error(s) found:

[FAIL] functionSpecification -> description
       Field required
       Fix: add or correct the 'description' field
```

---

### Layer 3 — Semantic (custom rules)

Beyond the schema, additional rules check that the content makes logical
sense within the AutoAPI meta model.

| Rule | ID | What it checks |
|---|---|---|
| FuSa requires ASIL | MR-FuSa | If `FuSa: true`, `ASIL` must be specified |
| FuSa false redundant ASIL | MR-FuSaASIL | If `FuSa: false`, `ASIL` should not be set *(warning)* |
| Unique interface names | MR-NameUnique | Two Data interfaces with the same VSS path |
| Unique parameter names | MR-ParamUnique | Two parameters with the same name |
| Parameter naming convention | MR-ParamNaming | Name must follow `Vehicle.<Domain>.<Parameter>` |
| Runnable naming convention | MR-RunnableNaming | `functionName` must follow `<FunctionName>.Init/.Step/.Terminate` |
| Execution result type | MR-ExecResult | `executionResult.type` must be `FunctionResult`, not `void` |
| Scheduling present | MR-Schedule | At least one runnable must be defined |
| Init runnable present | MR-Init | No `init` runnable *(advisory, optional)* |
| Terminate runnable present | MR-Terminate | No `terminate` runnable *(advisory, optional)* |

> **Errors** stop validation and block code generation.
> **Warnings** are shown but do not block — the file is still considered valid.

Example output:
```
[SEMANTIC ERRORS] 1 semantic rule violation(s):

[FAIL] [MR-ParamNaming] parameter 'RWS_deltaRAGradLim': name does not follow
       the hierarchical naming convention Vehicle.<Domain>.<Parameter>.
       Example: Vehicle.Chassis.MyFunction.GainFactor
```

---

## 5. Validated Output — What a Clean File Looks Like

When all checks pass, the validator shows a structured summary:

```
------------------------------------------------------------
File: speed_hazard_detection.afs
  [OK] Valid
  Function   : SpeedHazardDetection  v1.0.0
  Meta model : Eclipse-autoapiframework-Metamodel  v0.4.1
  Inputs     : 2
  Outputs    : 1
  Parameters : 2
  Runnables  : 3
------------------------------------------------------------
All 1 file(s) passed validation.
```

---

## 6. Real Bug Found During Development

During implementation, running the validator against the three existing
example `.afs` files in the repository found a **real bug** in
`vehicle_speed_fusion_multirate.afs` that was not caught by the existing
C++ syntax check:

```yaml
# Wrong — description placed inside metaModelRef:
metaModelRef:
    name: Eclipse-autoapiframework-Metamodel
    version: 0.4.1
    description: Fuses standard VSS wheel-speed inputs...   ← wrong location

# Correct — description at top level of functionSpecification:
functionSpecification:
  name: VehicleSpeedFusion
  description: Fuses standard VSS wheel-speed inputs...     ← correct location
```

The validator reported:
```
[FAIL] functionSpecification -> description
       Field required
       Fix: add or correct the 'description' field
```

This demonstrates the value of meta model-aware validation over basic YAML
syntax checking.

---

## 7. How to Run Validation

### Via Function Designer GUI

1. Open the **Function Designer** application
2. Load a `.afs` file via **Read .afs file**
3. Click **Syntax check**
4. The result appears in a single dialog:
   - Green information icon = all checks passed
   - Red error icon = one or more checks failed, with exact field locations

### Via Command Line

```bash
# Validate a single file
python validate_afs.py examples/speed_hazard_detection.afs

# Validate multiple files at once
python validate_afs.py examples/speed_hazard_detection.afs \
                       examples/wheel_speed_plausibility_check.afs

# Validate all .afs files (Linux/macOS)
find . -name "*.afs" | xargs python tools/validate_afs.py
```

Exit codes:
- `0` — all files valid
- `1` — one or more files failed

### Via CMake (CI/CD)

```bash
cmake --preset linux-gcc-release
cmake --build --preset linux-gcc-release --target validate_afs
```

Or via CTest (alongside C++ unit tests):
```bash
ctest --preset linux-gcc-release -R validate_afs
```

---

## 8. Integration in the CI/CD Pipeline

The validation target can be added to any CI/CD pipeline as a mandatory
step that runs on every pull request and every push to `main`.

```yaml
# Example GitHub Actions step
- name: Validate .afs files
  run: |
    pip install -r function_designer/tools/requirements.txt
    python function_designer/tools/validate_afs.py \
      function_designer/examples/speed_hazard_detection.afs \
      function_designer/examples/wheel_speed_plausibility_check.afs
```

A failing `.afs` file blocks the pull request from being merged — ensuring
that no non-conformant specification ever reaches the main branch.

---

## 9. Relationship to Code Generation

Validation and code generation are two steps of the same workflow:

```
.afs file
    ↓
validate_afs.py (Pydantic)     ← Step 1: Is the spec correct?
    ↓ pass
generate_adapter.py (Jinja2)   ← Step 2: Generate C++/C/Rust from spec
    ↓
SpeedHazardDetection.h + .cpp  ← Ready for the developer
```

The validator and the generator share the same Pydantic models (`afs_model.py`).
This guarantees that the data the generator receives has already been validated —
the generator never needs to check for missing fields or wrong types.

**Pydantic** is the gatekeeper — nothing incorrect gets through.
**Jinja2** is the factory — valid data in, correct code out.

---

## 10. Files

| File | Purpose |
|---|---|
| `tools/validate_afs.py` | Validation script — entry point |
| `tools/afs_model.py` | Pydantic models mirroring meta model v0.4.1 |
| `tools/requirements.txt` | Pinned dependencies: `pydantic==2.12.5`, `pyyaml==6.0.3`, `jinja2==3.1.6` |

When the meta model version changes, only `afs_model.py` needs to be updated.
The validator automatically picks up the changes — no C++ recompilation required.
