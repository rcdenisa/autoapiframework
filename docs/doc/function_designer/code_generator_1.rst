..
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
   #
   # Contributors:
   #   Denisa Ros - Code Generator 1 (Function API)
   # *******************************************************************************

Code Generator 1: Function API
==============================

Code Generator 1 creates the **Function API**, the middleware-independent
**interface contract** of one function, from its ``.afs`` file. It is a set of Jinja2
templates driven by ``tools/generate_adapter.py``.

The Function API only **declares** the interface: types, constants and methods. It
contains no implementation. The implementation of the API is the Function Adapter.

Status of the code generators
-----------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 40 18 20

   * - Generator
     - Output
     - Files
     - Status
   * - Code Generator 1
     - Function API (interface contract)
     - ``<function>_api.*``
     - Implemented
   * - Code Generator 2
     - Function Adapter (API implementation)
     - ``<function>_fad.*``
     - Under discussion
   * - Code Generator 3
     - Middleware Abstraction Layer
     - ``<function>_mw.*``
     - Under discussion

The content and the ownership of Code Generator 2 and 3 are not decided yet. The
folder layout below already reserves their place, but Code Generator 1 creates only
the ``api`` part.

Usage
-----

.. code-block:: powershell

   AutoAPIFunctionDesigner_CodeGen_1 speed_hazard_detection.afs
   AutoAPIFunctionDesigner_CodeGen_1 speed_hazard_detection.afs --language rust --output-dir out
   AutoAPIFunctionDesigner_CodeGen_1 f.afs --output-dir out --enums-dir shared/include

   # without the executable
   python generate_adapter.py ..\examples\speed_hazard_detection.afs --language cpp

.. list-table:: Options
   :header-rows: 1
   :widths: 25 75

   * - Option
     - Meaning
   * - ``--language cpp|c|rust``
     - Target language. Default: ``cpp``.
   * - ``--output-dir <dir>``
     - Root of the generated tree. Default: the ``generated`` folder of the
       ``function_designer`` project; the current directory if the project is not found.
   * - ``--enums-dir <dir>``
     - Folder for the shared enums file. Default: ``<output-dir>/<language>/common``.
   * - ``--skip-validation``
     - Do not run the full validation before generating.
   * - ``--help``, ``--version``
     - Show help or version.

In the GUI, the same generator runs with **Create API**. The output folder and the
enums folder can be set in *Settings*.

Exit codes: ``0`` code generated, ``1`` validation or generation failed, ``2`` usage
error.

Processing steps
----------------

1. The ``.afs`` file is fully validated (see :doc:`afs_validation`). If it is invalid,
   generation is aborted and nothing is written.
2. Every parameter must have a ``defaultValue``. A null value is accepted by the
   validation, but a constant cannot be generated without a value, so generation stops
   with an error that names the parameters.
3. The shared enums file is created if it is missing, and regenerated only when the
   meta model version in the ``.afs`` file differs from the one in the existing file.
4. The Function API template of the selected language is rendered and written.

Generated folder layout
-----------------------

.. code-block:: text

   generated/
   +-- cpp/
   |   +-- common/
   |   |   +-- autoapiframework_enums.h            <- Code Generator 1 (shared by all functions)
   |   +-- speed_hazard_detection/
   |       +-- api/
   |       |   +-- speed_hazard_detection_api.h    <- Code Generator 1
   |       +-- adapter/                            <- reserved: Code Generator 2 (_fad.h/.cpp)
   |       +-- middleware/                         <- reserved: Code Generator 3 (_mw.h/.cpp)
   +-- c/      same layout: speed_hazard_detection_api.h,  common/autoapiframework_enums.h
   +-- rust/   same layout: speed_hazard_detection_api.rs, common/autoapiframework_enums.rs

- One ``.afs`` file describes one function and gets one folder, named after the
  function in snake_case (``SpeedHazardDetection`` -> ``speed_hazard_detection``).
- Several functions generated into the same output folder share one ``common/``.
- The ``adapter/`` and ``middleware/`` folders are **not** created by Code Generator 1.
- The api file includes the enums file with a relative path
  (``../../common/autoapiframework_enums.h``), so no extra include directory is needed.

.. list-table:: File suffixes
   :header-rows: 1
   :widths: 15 85

   * - Suffix
     - Layer
   * - ``_api``
     - Function API (interface contract) - Code Generator 1
   * - ``_fad``
     - Function Adapter (API implementation) - Code Generator 2
   * - ``_mw``
     - Middleware Abstraction Layer - Code Generator 3

Mapping from ``.afs`` to the Function API
-----------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 28 25 25

   * - ``.afs``
     - C++
     - C
     - Rust
   * - ``name``
     - ``class SpeedHazardDetection``
     - prefix ``SpeedHazardDetection_``
     - ``trait SpeedHazardDetectionApi``
   * - Data interface, ``direction: input``
     - ``float Get_Vehicle_Speed() const``
     - ``float SpeedHazardDetection_Get_Vehicle_Speed(const ..._Context* ctx)``
     - ``fn get_vehicle_speed(&self) -> f32``
   * - Data interface, ``direction: output``
     - ``void Set_Vehicle_Body_Lights_Hazard_Request(bool value)``
     - ``void ..._Set_...(..._Context* ctx, bool value)``
     - ``fn set_...(&mut self, value: bool)``
   * - ``runtimeCompanion.qualityCode``
     - ``DataQuality Get_..._Qualifier() const`` / ``Set_..._Qualifier(...)``
     - ``..._Get_..._Qualifier(ctx)`` / ``..._Set_..._Qualifier(ctx, value)``
     - ``get_..._qualifier`` / ``set_..._qualifier``
   * - Parameter
     - ``static constexpr float kVehicle_Chassis_SpeedHazardForward = 10.0F;``
     - ``#define AUTOAPIFRAMEWORK_SPEEDHAZARDDETECTION_K...``
     - ``pub const K_VEHICLE_CHASSIS_SPEEDHAZARDFORWARD: f32``
   * - Scheduling entry
     - ``FunctionResult Init();`` / ``Step();`` / ``Terminate();``
     - ``FunctionResult SpeedHazardDetection_Step(..._Context* ctx)``
     - ``fn step(&mut self) -> FunctionResult``
   * - ``cycleTimeMs`` (cyclic)
     - ``static constexpr std::uint32_t kStepCycleTimeMs``
     - ``#define ..._STEP_CYCLE_TIME_MS``
     - ``pub const STEP_CYCLE_TIME_MS: u32``
   * - ``supervision.deadline.maxExecutionTimeMs``
     - ``kStepMaxExecutionTimeMs``
     - ``..._STEP_MAX_EXECUTION_TIME_MS``
     - ``STEP_MAX_EXECUTION_TIME_MS``

Further details:

- Only the runnables present in the ``.afs`` file are declared. Init, Step and
  Terminate are optional.
- Every lifecycle method returns ``FunctionResult`` (``success``, ``failure``,
  ``notAvailable``).
- ``unit``, ``min``, ``max`` and ``implementedASIL`` appear as comments next to the
  declarations.
- VSS names are turned into identifiers by replacing ``.`` with ``_``
  (``Vehicle.Speed`` -> ``Vehicle_Speed``); Rust uses lower case.

Data type mapping
~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 25 25 25

   * - ``dataType``
     - C++
     - C
     - Rust
   * - ``float`` / ``double``
     - ``float`` / ``double``
     - ``float`` / ``double``
     - ``f32`` / ``f64``
   * - ``int8`` ... ``int64``
     - ``std::int8_t`` ... ``std::int64_t``
     - ``int8_t`` ... ``int64_t``
     - ``i8`` ... ``i64``
   * - ``uint8`` ... ``uint64``
     - ``std::uint8_t`` ... ``std::uint64_t``
     - ``uint8_t`` ... ``uint64_t``
     - ``u8`` ... ``u64``
   * - ``boolean`` / ``bool``
     - ``bool``
     - ``bool``
     - ``bool``
   * - ``string``
     - ``const char*``
     - ``const char*``
     - ``&'static str``

Example (C++)
-------------

Extract of ``speed_hazard_detection_api.h`` generated from
``speed_hazard_detection.afs``:

.. code-block:: cpp

   #include "../../common/autoapiframework_enums.h"

   namespace autoapiframework {

   class SpeedHazardDetection
   {
   public:
       // Parameters (tunable: false)
       static constexpr float         kVehicle_Chassis_SpeedHazardForward      = 10.0F;   // percent [0.0 .. 100.0]
       static constexpr std::uint32_t kVehicle_Chassis_HazardRequestDurationMs = 3000U;   // ms [0 .. 600000]

       // Scheduling
       static constexpr std::uint32_t kStepCycleTimeMs = 20U;

       FunctionResult Init();       // runType: init,      ASIL B
       FunctionResult Step();       // runType: cyclic,    ASIL B, cycle 20 ms
       FunctionResult Terminate();  // runType: terminate, ASIL QM

       // Inputs
       float       Get_Vehicle_Speed() const;    // km/h [0.0 .. 300.0]
       DataQuality Get_Vehicle_Speed_Qualifier() const;
       ...
       // Outputs
       void Set_Vehicle_Body_Lights_Hazard_Request(bool value);
       void Set_Vehicle_Body_Lights_Hazard_Request_Qualifier(DataQuality value);
       ...
   };

   } // namespace autoapiframework

In C, the API is a set of functions on an opaque ``SpeedHazardDetection_Context``
handle; in Rust, it is the trait ``SpeedHazardDetectionApi``. The C context structure,
the Rust struct implementing the trait and all method bodies belong to the Function
Adapter.

Limitations
-----------

- Error interfaces (``errorInterfaces``, candidate interface type) are not yet read
  from the ``.afs`` file, so no code is generated for them. The templates already
  contain the parts for error interfaces.
- The cycle time constant has a fixed name (``kStepCycleTimeMs``). A function with
  more than one cyclic runnable would generate duplicate constants.
- The C++ API currently contains private member variables for the signal values.
  How the Function API and the Function Adapter are split exactly depends on the
  decisions for Code Generator 2.
