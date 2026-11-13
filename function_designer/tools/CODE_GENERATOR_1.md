# Code Generator 1 — API/Skeleton Generation

**Document status:** Draft v1.1
**Last updated:** 2026-11-12
**Project:** Eclipse Automotive API Framework
**Source:** [AutoAPI Framework Documentation](https://tompzf.github.io/autoapiframework/function_designer/doc/standardization/standardization.html)

---

## Summary

Code Generator 1 generates the **API/Skeleton** directly from a `.afs` Function
Specification File. It produces the complete, middleware-independent interface
that a vehicle function developer compiles against — including the class
definition, getter/setter methods for all signals, static constexpr parameters,
lifecycle method skeletons (`Init`, `Step`, `Terminate`), and the shared enums
file.

The generator supports **C++** (`.h` + `.cpp`), **C** (`.h` + `.c`), and
**Rust** (`.rs`), and runs validation against the meta model before generating
anything.

This covers exactly the **Code Generator 1 (Autoapiframework)** step from the
architecture diagram — taking the `.afs` as input and producing the API/Skeleton
that Code Generator 2 then uses to build the full Function Adapter.

---

## 1. Background

Developing automotive applications for microprocessor-based HPCs is challenging
because application code is often tightly coupled to the middleware and operating
system. Low-level middleware APIs require developers to write and maintain extensive
boilerplate for integration and testing, while also demanding deep automotive-specific
knowledge of the HPC software stack.

The **Eclipse Automotive API Framework** solves this by decoupling application logic
from the middleware stack, providing a standardized, middleware-independent
application-facing interface.

With a standardized application API:
- Application code remains stable across platform changes
- Only the generated middleware glue code changes per platform
- The application remains untouched and re-certifiable
- Platform-specific safety mechanisms are handled reliably by the generator

---

## 2. Why Code Generation Matters

Code generators play a critical role in the AutoAPI Framework workflow. From the
official documentation:

**1. Reduced Human Error**
Manually writing middleware-integration code is error-prone. A code generator
creates the same logic consistently and deterministically, eliminating typos,
incorrect API usage, inconsistent patterns, and forgotten safety checks.

**2. Enforced Safety Patterns**
Generators embed proven safety concepts: safe state handling, range checks,
timing and deadline monitoring hooks, memory-access restrictions, and exception
handling patterns required for ASIL levels. Every generated component has the
same safety mechanisms built in — no developer forgets to implement them.

**3. Traceability and ISO 26262 Compliance**
A generator enables automatic tracing from API model to generated code,
formally verified generation rules, consistent output across versions, and
compliance documentation for the generator itself. This reduces certification
effort for each project.

**4. Faster Updates and Refactoring**
When middleware or safety requirements change, the generator is updated once
and regenerates conformant code for all applications. No risk of missing manual
updates.

**5. Improved Testability**
Generated code is structurally predictable, easier to analyze automatically,
easier to unit-test (same patterns everywhere), and easier to integrate with
static analysis tools.

---

## 3. Workflow — Four Processing Steps

The AutoAPI Framework workflow consists of four processing steps.
**Steps 1 and 2 may be treated as a single combined step.**

```
Step 1 + 2 (Autoapiframework):
  .afs file ──▶ Code Generator 1 ──▶ API / Skeleton
                                           │
                                           ▼
Step 2 (middleware-specific):    Code Generator 2 ──▶ Function Adapter
                                                            │
Step 3 (middleware-specific):    Code Generator 3 ──▶ Middleware Abstraction
                                                            │
Step 4 (middleware-specific):    Code Generator  ──▶  Actuator & Sensor Services
                                                       Platform Abstraction
```

> **Important:** Code Generators 2, 3, and 4 are part of the **target middleware
> implementation** (S-CORE, Vector Adaptive AUTOSAR, etc.) and are **not** part of
> the Eclipse Autoapiframework. Only **Code Generator 1 is implemented within
> the Eclipse Autoapiframework.**

> **Note on diagram placement:** In some versions of the architecture diagram,
> Code Generator 1 may appear positioned after Code Generator 2. The correct
> placement is: **Code Generator 1 runs first**, directly from the `.afs` file,
> and produces the API/Skeleton. Code Generator 2 then uses that output together
> with the function implementation to produce the Function Adapter.

---

## 4. Technology — Why Jinja2 and Pydantic

Code Generator 1 is implemented in Python using two libraries:
**Jinja2** for code generation and **Pydantic** for validation.

### Jinja2 — the code generator

Jinja2 is a Python template engine. A template is a plain text file
that contains the structure of the output (C++, C, or Rust) with
placeholders that are filled in at generation time:

```jinja2
class {{ spec.name }}                          ← filled with "SpeedHazardDetection"
{
public:
{% for p in params %}
    static constexpr {{ p.dataType | cpp_type }} k{{ p.name | cpp_identifier }}
        = {{ p.defaultValue | cpp_suffix(p.dataType) }};
{% endfor %}
```

**Why Jinja2 was chosen:**

| Criteria | Jinja2 | Alternative |
|---|---|---|
| Same input → always same output | Yes — deterministic | AI generation: non-deterministic |
| Template readable by any developer | Yes — plain text file | String concatenation: hard to read |
| Template change requires recompile | No — edit and run | C++ generator: yes |
| Used in COVESA/Eclipse SDV ecosystem | Yes — vss-tools, IFEX | No established alternative |
| ISO 26262 qualifiable | Yes — deterministic, inspectable | AI: not qualifiable |

Jinja2 is already used by `vss-tools` (a direct dependency of this project)
and by COVESA IFEX — the interface exchange format referenced in the AutoAPI
documentation. Adopting Jinja2 does not introduce a new technology into the
ecosystem — it aligns with what every adjacent project already uses.

**Why not AI for generation:**
AI generates probabilistic output — the same `.afs` file can produce different
C++ code on different runs. This violates the reproducibility requirement of
automotive build pipelines and cannot be qualified under ISO 26262. AI is
useful for authoring `.afs` files or templates, but never for the generation
step in a build pipeline.

---

### Pydantic — the validator

Before generating code, the `.afs` file is validated against the meta model
using **Pydantic v2**. Pydantic expresses the meta model as Python classes
with type annotations. Loading a YAML file through a Pydantic model
automatically checks every field — types, mandatory presence, enum values,
and conditional rules.

The generator never needs to handle missing or incorrect data — Pydantic
ensures the data is correct before the templates ever see it.

For full details on validation, see `AFS_VALIDATION.md`.

---

### How Python integrates with the C++ application

The generator and validator are standalone Python scripts. The C++ Function
Designer application calls them as external processes using `wxExecute` —
the same mechanism already used to call `vspec` (COVESA VSS tool).

```
User clicks "Create API" in Function Designer (C++)
        ↓
C++ calls: python generate_adapter.py file.afs --language cpp --output-dir ...
        ↓
Python/Pydantic validates the .afs file
        ↓
Python/Jinja2 renders the template with validated data
        ↓
.h and .cpp files written to the output directory
        ↓
C++ reads the exit code and displays result in dialog
```

**The boundary is clear:**
- C++ owns the GUI, the YAML parser, the runtime application
- Python owns the meta model validation and the code generation templates
- Python never runs on the target ECU — only the generated C++/Rust does

When the meta model changes, only `afs_model.py` (Pydantic models) needs
updating. The templates and the C++ application do not need to change.

---

## 5. Code Generator 1 — Purpose and Scope

**Code Generator 1** reads a Function Specification File (`.afs`) and produces
the **API/Skeleton** — the complete, middleware-independent interface that the
vehicle function developer compiles against.

```
┌─────────────────────┐       ┌──────────────────────┐       ┌─────────────────────┐
│    .afs file        │──────▶│   Code Generator 1   │──────▶│    API / Skeleton   │
│ (Function Spec)     │       │  (Autoapiframework)   │       │  .h + .cpp / .rs    │
└─────────────────────┘       └──────────────────────┘       └─────────────────────┘
```

The developer **never writes this boilerplate by hand**. Everything is derived
directly and deterministically from the specification file.

The generated API/Skeleton:
- Provides the complete class/struct interface
- Includes all getter and setter methods for signals
- Initializes outputs to safe defaults in `Init()` and `Terminate()`
- Provides a `Step()` skeleton with a `// TODO` for the developer's logic
- Is the same regardless of the target middleware

---

## 6. Input — Function Specification File (`.afs`)

A `.afs` file is a YAML document that describes exactly **one** software function:
what signals it reads, what signals it writes, its parameters, and how its
runnables are scheduled.

Code Generator 1 uses the following sections:

---

### 5.1 Function Identity

```yaml
functionSpecification:
  name: SpeedHazardDetection          # → class name
  version: 1.0.0                      # → header comment
  description: >-
    Detects rapid acceleration...     # → documentation comment
  metaModelRef:
    name: Eclipse-autoapiframework-Metamodel
    version: 0.4.1
```

| Field | Used for |
|---|---|
| `name` | Class name (`class SpeedHazardDetection`) and namespace |
| `version` | File header comment |
| `description` | Documentation comment in generated file |

---

### 5.2 Data Interfaces — Signals

```yaml
dataInterfaces:
  - name: Vehicle.Speed               # VSS path → identifier
    direction: input                  # input → getter method
    dataType: float                   # → C++ type: float
    unit: km/h                        # → documentation comment
    min: 0.0                          # → documentation comment
    max: 300.0                        # → documentation comment
    defaultValue: 0.0                 # → private member default value
    FuSa: true
    ASIL: B                           # → documentation comment
    runtimeCompanion:
      qualityCode:
        name: Vehicle.Speed.Qualifier # → additional qualifier getter
```

| `.afs` field | Effect on generated code |
|---|---|
| `direction: input` | Generates `Get_Vehicle_Speed() const` getter method |
| `direction: output` | Generates `Set_Vehicle_Body_Lights_Hazard_Request(value)` setter method |
| `dataType` | Mapped to correct language type (`float`, `bool`, `std::uint32_t`, ...) |
| `defaultValue` | Initializes private member variable (`= 0.0F`) |
| `runtimeCompanion.qualityCode` | Generates additional `Get_..._Qualifier()` / `Set_..._Qualifier()` method |
| `unit`, `min`, `max`, `ASIL` | Appear in inline documentation comments |

---

### 5.3 Parameters

```yaml
parameters:
  - name: Vehicle.Chassis.SpeedHazardForward
    dataType: float
    defaultValue: 10.0
    unit: percent
    min: 0.0
    max: 100.0
    tunable: false
```

| `.afs` field | Effect on generated code |
|---|---|
| `name` | `static constexpr float kVehicle_Chassis_SpeedHazardForward` |
| `defaultValue` | `= 10.0F` |
| `unit`, `min`, `max` | Appear in inline documentation comment |
| `tunable` | Shown in Parameters section comment |

---

### 5.4 Scheduling

```yaml
scheduling:
  - functionName: SpeedHazardDetection.Init     # → Init() method
    runType: init
    implementedASIL: B

  - functionName: SpeedHazardDetection.Step     # → Step() method
    runType: cyclic
    cycleTimeMs: 20                             # → kStepCycleTimeMs = 20U

  - functionName: SpeedHazardDetection.Terminate
    runType: terminate
    implementedASIL: QM
```

| `.afs` field | Effect on generated code |
|---|---|
| `functionName` | Method name (`Init`, `Step`, `Terminate`) |
| `runType: init` | `Init()` is pre-filled: sets outputs to safe defaults |
| `runType: cyclic` | `Step()` contains `// TODO:` placeholder for developer logic |
| `runType: terminate` | `Terminate()` is pre-filled: sets outputs to defaults, qualifiers to invalid |
| `cycleTimeMs` | `static constexpr std::uint32_t kStepCycleTimeMs = 20U` |
| `implementedASIL` | Appears in inline documentation comment |
| All methods | Return `FunctionResult` (success / failure / notAvailable) |

---

### 5.5 Error Interfaces *(candidate — if present)*

```yaml
errorInterfaces:
  - name: WheelSpeedPlausibilityCheck.RangeError.ErrorStatus
    dataType: boolean
    severity: degraded
    maturationTimeMs: 100
    resetTimeMs: 200
```

| `.afs` field | Effect on generated code |
|---|---|
| `name` | `Set_WheelSpeedPlausibilityCheck_RangeError_ErrorStatus(bool value)` |
| `severity` | `static constexpr ErrorSeverity k..._Severity = ErrorSeverity::degraded` |
| `maturationTimeMs` | `static constexpr std::uint32_t k..._MaturationTimeMs = 100U` |
| `resetTimeMs` | `static constexpr std::uint32_t k..._ResetTimeMs = 200U` |

> Error interfaces have **candidate status** in the current meta model (v0.4.1)
> and may evolve in future versions.

---

## 7. Output — Generated Files

### 6.1 C++ (`.h` + `.cpp`)

**Input:** `speed_hazard_detection.afs`

#### `SpeedHazardDetection.h`

```cpp
// Generated from speed_hazard_detection.afs (metamodel Eclipse-autoapiframework-Metamodel 0.4.1)
// SPDX-License-Identifier: Apache-2.0

#pragma once
#include <cstdint>
#include "autoapiframework_enums.h"

namespace autoapiframework {

// ---------------------------------------------------------------------------
// Function: SpeedHazardDetection 1.0.0
// Detects rapid acceleration and requests hazard warning lights if the
// configured threshold is exceeded.
// ---------------------------------------------------------------------------
class SpeedHazardDetection
{
public:
    // Parameters (tunable: false)
    static constexpr float          kVehicle_Chassis_SpeedHazardForward      = 10.0F;  // percent [0.0 .. 100.0]
    static constexpr std::uint32_t  kVehicle_Chassis_HazardRequestDurationMs = 3000U;  // ms [0 .. 600000]

    // Scheduling
    static constexpr std::uint32_t kStepCycleTimeMs = 20U;

    SpeedHazardDetection() = default;

    FunctionResult Init();       // runType: init,      ASIL B
    FunctionResult Step();       // runType: cyclic,    ASIL B, cycle 20 ms
    FunctionResult Terminate();  // runType: terminate, ASIL QM

    // Inputs
    float       Get_Vehicle_Speed() const;                       // km/h [0.0 .. 300.0]
    DataQuality Get_Vehicle_Speed_Qualifier() const;
    float       Get_Vehicle_Acceleration_Longitudinal() const;   // m/s2 [-20.0 .. 20.0]
    DataQuality Get_Vehicle_Acceleration_Longitudinal_Qualifier() const;

    // Outputs
    void Set_Vehicle_Body_Lights_Hazard_Request(bool value);
    void Set_Vehicle_Body_Lights_Hazard_Request_Qualifier(DataQuality value);

private:
    // Input storage
    float        m_Vehicle_Speed                                    = 0.0F;
    DataQuality  m_Vehicle_Speed_Qualifier                          = DataQuality::uninitialized;
    float        m_Vehicle_Acceleration_Longitudinal                = 0.0F;
    DataQuality  m_Vehicle_Acceleration_Longitudinal_Qualifier      = DataQuality::uninitialized;

    // Output storage
    bool         m_Vehicle_Body_Lights_Hazard_Request               = false;
    DataQuality  m_Vehicle_Body_Lights_Hazard_Request_Qualifier     = DataQuality::uninitialized;
};

} // namespace autoapiframework
```

#### `SpeedHazardDetection.cpp`

```cpp
// Generated from speed_hazard_detection.afs ...

#include "SpeedHazardDetection.h"

namespace autoapiframework {

FunctionResult SpeedHazardDetection::Init()
{
    // Outputs set to safe defaults
    Set_Vehicle_Body_Lights_Hazard_Request(false);
    Set_Vehicle_Body_Lights_Hazard_Request_Qualifier(DataQuality::uninitialized);
    return FunctionResult::success;
}

FunctionResult SpeedHazardDetection::Step()
{
    // TODO: implement SpeedHazardDetection logic   ← developer fills this in
    return FunctionResult::success;
}

FunctionResult SpeedHazardDetection::Terminate()
{
    Set_Vehicle_Body_Lights_Hazard_Request(false);
    Set_Vehicle_Body_Lights_Hazard_Request_Qualifier(DataQuality::invalid);
    return FunctionResult::success;
}

float SpeedHazardDetection::Get_Vehicle_Speed() const
{
    return m_Vehicle_Speed;
}

// ... all getter and setter implementations generated
} // namespace autoapiframework
```

---

### 6.2 C (`.h` + `.c`)

C output uses function prefixes instead of a class, `#define` macros for
parameters, and an opaque context handle to hide internal state.

```c
/* Generated from speed_hazard_detection.afs ... */

#define AUTOAPIFRAMEWORK_SPEEDHAZARDDETECTION_KVEHICLE_CHASSIS_SPEEDHAZARDFORWARD    (10.0F)
#define AUTOAPIFRAMEWORK_SPEEDHAZARDDETECTION_STEP_CYCLE_TIME_MS                     (20U)

/* Opaque context — internal state hidden from the caller */
typedef struct SpeedHazardDetection_Context SpeedHazardDetection_Context;

FunctionResult SpeedHazardDetection_Init(SpeedHazardDetection_Context* ctx);
FunctionResult SpeedHazardDetection_Step(SpeedHazardDetection_Context* ctx);
FunctionResult SpeedHazardDetection_Terminate(SpeedHazardDetection_Context* ctx);

float       SpeedHazardDetection_Get_Vehicle_Speed(const SpeedHazardDetection_Context* ctx);
DataQuality SpeedHazardDetection_Get_Vehicle_Speed_Qualifier(const SpeedHazardDetection_Context* ctx);

void SpeedHazardDetection_Set_Vehicle_Body_Lights_Hazard_Request(
    SpeedHazardDetection_Context* ctx, bool value);
```

---

### 6.3 Rust (`.rs`)

Rust output uses a struct with private fields, a `Default` implementation,
and an `impl` block with public getter/setter methods.

```rust
// Generated from speed_hazard_detection.afs ...

pub const K_VEHICLE_CHASSIS_SPEEDHAZARDFORWARD: f32 = 10.0_f32;
pub const STEP_CYCLE_TIME_MS: u32 = 20_u32;

pub struct SpeedHazardDetection {
    vehicle_speed: f32,
    vehicle_speed_qualifier: DataQuality,
    vehicle_acceleration_longitudinal: f32,
    vehicle_body_lights_hazard_request: bool,
    // ...
}

impl SpeedHazardDetection {
    pub fn init(&mut self) -> FunctionResult { /* pre-filled */ }
    pub fn step(&mut self) -> FunctionResult {
        // TODO: implement SpeedHazardDetection logic
        FunctionResult::Success
    }
    pub fn terminate(&mut self) -> FunctionResult { /* pre-filled */ }

    pub fn get_vehicle_speed(&self) -> f32 { self.vehicle_speed }
    pub fn set_vehicle_body_lights_hazard_request(&mut self, value: bool) { ... }
}
```

---

## 8. Full Mapping Table: `.afs` → Generated Code

| `.afs` | C++ | C | Rust |
|---|---|---|---|
| `name` | `class SpeedHazardDetection` | `SpeedHazardDetection_*` prefix | `struct SpeedHazardDetection` |
| `direction: input` | `float Get_Vehicle_Speed() const` | `..._Get_Vehicle_Speed(ctx)` | `pub fn get_vehicle_speed(&self)` |
| `direction: output` | `void Set_...(bool value)` | `..._Set_...(ctx, value)` | `pub fn set_...(&mut self, value)` |
| `runtimeCompanion` | `DataQuality Get_..._Qualifier()` | `DataQuality ..._Get_..._Qualifier(ctx)` | `pub fn get_..._qualifier(&self)` |
| `parameter` | `static constexpr float k... = 10.0F` | `#define ... (10.0F)` | `pub const K_...: f32 = 10.0_f32` |
| `runType: init` | `FunctionResult Init()` — pre-filled | `..._Init(ctx)` — pre-filled | `pub fn init(&mut self)` — pre-filled |
| `runType: cyclic` | `FunctionResult Step()` + `kStepCycleTimeMs` | `..._Step(ctx)` + `#define` | `pub fn step(&mut self)` + `const` |
| `runType: terminate` | `FunctionResult Terminate()` — pre-filled | `..._Terminate(ctx)` — pre-filled | `pub fn terminate(&mut self)` — pre-filled |
| `errorInterfaces` | `void Set_..._ErrorStatus(bool)` + `static constexpr` | `#define` + setter | `pub fn set_...` + `pub const` |

---

## 9. What the Developer Does After Generation

Code Generator 1 produces a complete, compilable skeleton. The developer's only
mandatory task is to implement the `Step()` function with the business logic:

```cpp
FunctionResult SpeedHazardDetection::Step()
{
    // Read inputs
    const float speed = Get_Vehicle_Speed();
    const float accel = Get_Vehicle_Acceleration_Longitudinal();

    // Apply function logic
    const bool hazard = (accel > kVehicle_Chassis_SpeedHazardForward / 100.0F * speed);

    // Write outputs
    Set_Vehicle_Body_Lights_Hazard_Request(hazard);
    Set_Vehicle_Body_Lights_Hazard_Request_Qualifier(DataQuality::valid);

    return FunctionResult::success;
}
```

`Init()` and `Terminate()` are pre-filled with safe defaults and do not
require modification unless the function has specific startup/shutdown logic.

---

## 10. How to Generate

### Via Function Designer GUI

1. Open the **Function Designer** application
2. Click **Read .afs file** and open a `.afs` specification
3. Click **Syntax check** to validate the file first
4. Click **Create API**
5. Select target language: **C++**, **C**, or **Rust**
6. Choose an output directory
7. The generated files appear immediately in the selected directory

### Via Command Line

```bash
python generate_adapter.py <path/to/file.afs> --language cpp  --output-dir ./output
python generate_adapter.py <path/to/file.afs> --language c    --output-dir ./output
python generate_adapter.py <path/to/file.afs> --language rust --output-dir ./output
```

The `.afs` file is validated against the meta model before generation.
If the file contains errors, generation is stopped and all errors are reported
with exact field locations and fix hints.

---

## 11. Relationship to Other Code Generators

| Generator | Part of | Input | Output |
|-----------|---------|-------|--------|
| **Code Generator 1** *(this document)* | **Eclipse Autoapiframework** | `.afs` file | API/Skeleton (`.h`, `.cpp`, `.rs`) |
| Code Generator 2 | Target middleware | `.afs` + function code | Function Adapter |
| Code Generator 3 | Target middleware | `.afs` | Middleware Abstraction |
| Other generators | Target middleware | `vspec`, `.dbc` | Actuator/Sensor Services, Platform Abstraction |

Code Generator 1 output is **middleware-independent** — the same generated
interface works regardless of whether the target is VAPI, S-CORE, or
Vector Adaptive AUTOSAR. Middleware-specific code is produced only by
the generators that belong to each respective middleware implementation.
