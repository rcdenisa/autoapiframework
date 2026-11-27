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
   #   Denisa Ros - Tool selection for validation and code generation
   # *******************************************************************************

Tool Selection
==============

This page explains why the Python tooling (see :doc:`python_tooling`) uses
**Pydantic** for validation and **Jinja2** for code generation, and which
alternatives were evaluated.

The tools run only at build time, on a development machine or in CI. Their output
is C++, C or Rust source code; nothing from the Python tooling runs on the target
ECU. In short: *Python generates, C++ and Rust execute.*

Requirements
------------

The alternatives were compared against the following requirements:

.. list-table:: Requirements for the tooling
   :header-rows: 1
   :widths: 8 22 70

   * - ID
     - Requirement
     - Rationale
   * - R1
     - Deterministic
     - The same ``.afs`` file always produces exactly the same output. Needed for
       reproducible builds and for reviewing generated code as a diff.
   * - R2
     - Auditable
     - The validation rules and the generation logic can be read and reviewed by
       any developer.
   * - R3
     - Ecosystem fit
     - Fits the COVESA / Eclipse SDV tooling the framework is part of.
   * - R4
     - Maintainable
     - A meta model update is made in one place.
   * - R5
     - Offline
     - No internet connection, API key or external service needed to validate or
       generate.
   * - R6
     - Qualifiable
     - Can be qualified under ISO 26262-8 if a certified pipeline requires it.

Validation: Pydantic
--------------------

Pydantic describes the meta model as Python classes with type annotations
(``tools/afs_model.py``). Loading an ``.afs`` file through these classes checks
mandatory keys, types and enum values automatically; conditional rules are small
validator methods. Errors are reported with their location in the file.

.. list-table:: Alternatives evaluated for validation
   :header-rows: 1
   :widths: 22 78

   * - Alternative
     - Why not chosen
   * - Extend the C++ syntax check (``validate_function.cpp``)
     - Every rule needs hand-written checks and error messages, and every meta model
       change needs C++ changes and a rebuild. The check cannot run in CI without
       building the application. It remains in use in the GUI (see below).
   * - JSON Schema + ``jsonschema``
     - Language independent, but conditional rules (for example "``cycleTimeMs`` is
       required when ``runType`` is ``cyclic``") are hard to express and to read.
       A separate schema file would have to be kept in sync with the meta model.
   * - Marshmallow
     - Mature, but more verbose than Pydantic v2 and without type annotations.
   * - Cerberus
     - Simple dictionary schemas; less expressive for nested models, smaller
       community.
   * - attrs + cattrs
     - Usable, but less convenient for deeply nested models with validation
       rules.
   * - CUE
     - Powerful schema language, but its own language and toolchain, which adds a
       dependency without a benefit at this stage.

**Result:** the whole meta model 0.4.1 fits in about 300 lines of Python, and a
meta model update changes only ``afs_model.py``; the validator and Code Generator 1
both use it. When the validator was first run on the example files, it found a
``description`` placed inside ``metaModelRef`` in
``vehicle_speed_fusion_multirate.afs``, which the existing syntax check had not
reported (fixed since).

Code generation: Jinja2
-----------------------

A Jinja2 template is a text file with the structure of the generated code and
placeholders filled from the validated specification.

.. list-table:: Alternatives evaluated for code generation
   :header-rows: 1
   :widths: 22 78

   * - Alternative
     - Why not chosen
   * - Mako
     - Similar features to Jinja2, but not used in the COVESA ecosystem; no
       advantage for this use case.
   * - Cheetah3
     - Older, little activity and adoption.
   * - Mustache / Handlebars
     - Logic-less templates: no expressions or filters, which C++, C and Rust
       generation needs (type mapping, identifiers, literal suffixes).
   * - Acceleo (Eclipse, Java)
     - Established for model-to-text generation in AUTOSAR tooling, but needs a JVM
       and the Eclipse Modeling Framework: too heavy for this project. Worth
       reconsidering only for a certified pipeline (see below).
   * - T4 templates (.NET)
     - Bound to the .NET / Visual Studio ecosystem; not cross-platform.
   * - Python string formatting (f-strings)
     - No extra dependency, but layout and logic are mixed in the code and become
       hard to maintain for several languages and files.
   * - C++ template engine (for example ``inja``) in the Function Designer
     - Every template change would need a rebuild of the application, and the
       generator could not be used without the GUI.

**Ecosystem:** Jinja2 is already used by COVESA ``vss-tools``, which the Function
Designer uses to import ``.vspec`` files, and by COVESA IFEX. Choosing it adds no new
technology to the ecosystem.

PyYAML, the third package, only loads the YAML content and was already used in the
project.

Why Python and not C++
----------------------

C++ is not replaced: the Function Designer GUI, its YAML parser and its syntax check
stay in C++, and the generated code is C++, C or Rust. Python is used only for the
build-time steps, because:

- validation and generation can run without the GUI, from the command line and in CI;
- templates and rules change without recompiling the application;
- the same validated model is shared by the validator and the generator.

Why not AI
----------

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Property
     - Jinja2 / Pydantic
     - AI (LLM)
   * - Same input, same output
     - Yes
     - No, output varies between runs and model versions
   * - Reviewable logic
     - Templates and classes are plain text
     - Not inspectable
   * - Offline
     - Yes
     - Usually needs an external service
   * - Qualifiable (ISO 26262-8)
     - The output can be verified by tests against expected files
     - Not reproducible, so not qualifiable in the same way

AI remains useful as a development assistant: to draft ``.afs`` files, to write or
change templates, or to analyse generated code. It is not part of the validation or
generation step.

When to revisit the decision
----------------------------

A different generator, for example a qualified C++ or Acceleo based one, would make
sense if:

- the tools must run where Python is not available;
- ISO 26262 tool qualification (TCL 2/3) is required and the organisation has a
  qualified toolchain other than Python.

Neither applies at the current stage of the project.

References
----------

- COVESA vss-tools: https://github.com/COVESA/vss-tools
- COVESA IFEX: https://github.com/COVESA/ifex
- Pydantic: https://docs.pydantic.dev
- Jinja2: https://jinja.palletsprojects.com
- ISO 26262-8, clause 11: confidence in the use of software tools
