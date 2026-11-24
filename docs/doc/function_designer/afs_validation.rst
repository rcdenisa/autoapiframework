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
   #   Denisa Ros - AFS validation with Pydantic
   # *******************************************************************************

AFS Validation
==============

The validation answers one question: **does this** ``.afs`` **file follow the meta
model rules?** It runs before any code is generated. If a file is invalid, Code
Generator 1 writes nothing and reports the errors.

Validation is implemented in ``tools/validate_afs.py`` with the Pydantic models in
``tools/afs_model.py`` (meta model 0.4.1). See :doc:`python_tooling` for the choice of
libraries.

Usage
-----

.. code-block:: powershell

   AutoAPIFunctionDesigner_ValidateAFS speed_hazard_detection.afs
   AutoAPIFunctionDesigner_ValidateAFS a.afs b.afs c.afs

   # without the executable
   python validate_afs.py ..\examples\speed_hazard_detection.afs

A file that is not found at the given path is also looked up next to the executable,
where the build copies the example files. Nothing is written.

.. list-table:: Exit codes
   :header-rows: 1
   :widths: 15 85

   * - Code
     - Meaning
   * - ``0``
     - All files are valid.
   * - ``1``
     - At least one file is invalid.
   * - ``2``
     - Usage error (wrong arguments, file not found).

Checks
------

The checks run in the order below. Each step stops the validation of the file if it
fails.

1. YAML loading
~~~~~~~~~~~~~~~

The file is loaded with PyYAML. A YAML syntax error is reported as ``[YAML ERROR]``.

2. Structure (Pydantic)
~~~~~~~~~~~~~~~~~~~~~~~

The content is validated against the models in ``afs_model.py``:

.. list-table:: Structural checks
   :header-rows: 1
   :widths: 35 65

   * - Check
     - Example of what is reported
   * - Mandatory key present
     - ``unit`` key missing in a Data interface
   * - Value type
     - ``minUpdatePeriodMs: fast`` - a number is expected
   * - Enum value
     - ``ASIL: X`` - must be ``QM``, ``A``, ``B``, ``C`` or ``D``
   * - ``cycleTimeMs`` for cyclic runnables
     - ``runType: cyclic`` without ``cycleTimeMs``
   * - Supervision type
     - ``supervision.required: true`` without ``supervision.type``

The enum checks cover ``ASIL``, ``Direction``, ``RunType``, ``ErrorSeverity`` and
``SupervisionType`` as defined in the meta model.

Example output:

.. code-block:: text

   [SCHEMA ERRORS] 1 structural error(s) found:

   [FAIL] functionSpecification -> dataInterfaces -> 0 -> description
       Field required

Null rule for mandatory properties
""""""""""""""""""""""""""""""""""

A mandatory property must always be **present** in the ``.afs`` file. If its value is
not known yet, the key is written with an empty (null) value:

.. code-block:: yaml

   unit:

Such a value is accepted and means "not yet defined". The successful result lists
these properties as a note.

Only the properties that the code generator cannot work without need a real value:
``name``, ``functionName``, ``dataType``, ``direction`` and ``runType``, plus the
function ``version`` and ``metaModelRef``. The C++ syntax check of the Function
Designer applies the same rule.

3. Semantic rules
~~~~~~~~~~~~~~~~~

Rules that go beyond the structure of a single field:

.. list-table:: Semantic rules (errors)
   :header-rows: 1
   :widths: 22 78

   * - Rule
     - What it checks
   * - ``MR-FuSa``
     - If ``FuSa: true``, ``ASIL`` must be specified for the Data interface.
   * - ``MR-NameUnique``
     - Data interface names are unique.
   * - ``MR-ParamUnique``
     - Parameter names are unique.
   * - ``MR-Schedule``
     - At least one scheduling entry exists.

Example output:

.. code-block:: text

   [SEMANTIC ERRORS] 1 semantic rule violation(s):

   [FAIL] [MR-FuSa] dataInterface 'Vehicle.Speed': FuSa=True but ASIL is not specified.

4. Advisories
~~~~~~~~~~~~~

Advisories are shown but never make a file invalid:

.. list-table:: Advisories
   :header-rows: 1
   :widths: 22 78

   * - Rule
     - What it reports
   * - ``MR-Init``
     - No ``init`` runnable in ``scheduling``. Init is optional.
   * - ``MR-Terminate``
     - No ``terminate`` runnable in ``scheduling``. Terminate is optional.
   * - Empty mandatory properties
     - Mandatory properties with a null value (see the null rule above).

Result of a valid file
----------------------

.. code-block:: text

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

Relation to the C++ syntax check
--------------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 37 38

   * -
     - ``AutoAPIFunctionDesigner_SyntaxCheck``
     - ``AutoAPIFunctionDesigner_ValidateAFS``
   * - Implementation
     - C++ (``validate_function.cpp``)
     - Python, Pydantic (``validate_afs.py``)
   * - Meta model source
     - Reads the meta model YAML at run time
     - Python models in ``afs_model.py`` that mirror meta model 0.4.1
   * - Semantic rules
     - -
     - ``MR-*`` rules listed above
   * - Used before code generation
     - No
     - Yes, always (unless ``--skip-validation`` is passed to Code Generator 1)

Limitations
-----------

- The Pydantic models mirror meta model 0.4.1 by hand. When the meta model changes,
  ``afs_model.py`` must be updated as well.
- ``errorInterfaces`` (candidate interface type) is not yet read by the validation;
  the model currently expects the key ``errors``.
- Function-specific ``enums`` and ``enumRef`` references are not checked yet.
- Unknown keys are ignored, so a misspelled optional key is not reported.
