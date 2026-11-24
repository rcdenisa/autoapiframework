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
   #   Denisa Ros - Python tooling for validation and code generation
   # *******************************************************************************

Python Tooling: Validation and Code Generation
==============================================

The folder ``function_designer/tools`` contains the Python tooling that adds two
build-time steps to the Function Designer workflow:

1. **Validation** - checks that an ``.afs`` file conforms to the meta model before it
   is used by any code generator. See :doc:`afs_validation`.
2. **Code generation** - Code Generator 1 creates the Function API (interface
   contract) from a valid ``.afs`` file. See :doc:`code_generator_1`.

The tooling runs only on the development machine or in CI. Nothing in this folder
runs on the target ECU; the output consists of generated source files.

.. code-block:: text

   .afs file
      |
      v
   validation (Pydantic)          Is the specification correct?
      |  valid
      v
   Code Generator 1 (Jinja2)      Function API: <function>_api.h / .rs
                                  + shared autoapiframework_enums file

Libraries
---------

.. list-table:: Python dependencies
   :header-rows: 1
   :widths: 20 12 68

   * - Package
     - Version
     - Role
   * - ``pydantic``
     - 2.11.4
     - Describes the ``.afs`` content as typed Python classes and validates it
       (mandatory keys, types, enum values, conditional rules).
   * - ``jinja2``
     - 3.1.6
     - Template engine that turns the validated specification into C++, C or Rust code.
   * - ``pyyaml``
     - 6.0.2
     - Loads the ``.afs`` YAML content.
   * - ``pyinstaller``
     - 6.16.0
     - Build time only: freezes the scripts into stand-alone executables, so no
       Python installation is needed to run them.

The versions are pinned in ``tools/requirements.txt`` and
``tools/requirements-build.txt``.

Why Pydantic
~~~~~~~~~~~~

Pydantic expresses the meta model as Python classes with type annotations
(``tools/afs_model.py``). Loading a YAML file through these classes checks every
field automatically and reports errors with the exact location in the file, for
example ``functionSpecification -> dataInterfaces -> 0 -> unit``.

- **Little code per rule** - mandatory keys, types and enum values follow from the
  class definitions; conditional rules are small validator methods.
- **One place to update** - when the meta model changes, ``afs_model.py`` is updated
  and the validator and the generator both use the new definition.
- **Runs without the GUI** - the same check works from the command line and in CI.

Pydantic complements the C++ syntax check of the Function Designer
(``validate_function.cpp``), which reads the meta model YAML at run time.

Why Jinja2
~~~~~~~~~~

A Jinja2 template is a text file with the structure of the generated code and
placeholders that are filled from the specification:

.. code-block:: jinja

   class {{ spec.name }}
   {
   public:
   {% for p in params %}
       static constexpr {{ p.dataType | cpp_type }} k{{ p.name | cpp_identifier }} = {{ p.defaultValue | cpp_suffix(p.dataType) }};
   {% endfor %}

- **Deterministic** - the same ``.afs`` file always produces the same code, which is
  required for reproducible automotive builds and for reviewing generated code.
- **Readable** - templates look like the code they generate and can be changed without
  recompiling anything.
- **Already used in the ecosystem** - COVESA ``vss-tools`` (already a dependency of the
  Function Designer) and IFEX use Jinja2 as well.

Why not AI for these steps
~~~~~~~~~~~~~~~~~~~~~~~~~~

Validation and generation must give the same result for the same input every time.
AI models are probabilistic, so their output cannot be reproduced or qualified in the
same way. AI can help to write ``.afs`` files or templates, but it is not part of the
validation or generation step.

Files
-----

.. list-table:: Content of ``function_designer/tools``
   :header-rows: 1
   :widths: 35 65

   * - File
     - Purpose
   * - ``afs_model.py``
     - Pydantic models of the ``.afs`` content (meta model 0.4.1).
   * - ``validate_afs.py``
     - Validation; source of ``AutoAPIFunctionDesigner_ValidateAFS``.
   * - ``generate_adapter.py``
     - Code Generator 1; source of ``AutoAPIFunctionDesigner_CodeGen_1``.
   * - ``afs_common.py``
     - Helpers shared by both tools (exit codes, argument parsing, file lookup).
   * - ``build_exe.py``
     - Freezes a script into an executable with PyInstaller (called by CMake).
   * - ``templates/api*.jinja2``
     - Function API templates for C++, C and Rust.
   * - ``templates/autoapiframework_enums*.jinja2``
     - Templates for the shared enums file.
   * - ``templates/codegen2/``
     - Drafts kept as a starting point for Code Generator 2. Not used by Code Generator 1.

Integration with the Function Designer
--------------------------------------

The tools are used in three ways, always with the same validation rules:

- **GUI** - *Syntax check* and *Create API* in the Function Designer call the
  executables ``AutoAPIFunctionDesigner_ValidateAFS`` and
  ``AutoAPIFunctionDesigner_CodeGen_1`` located next to the application. If they are
  not found, the GUI runs the Python scripts from ``tools/`` with the Python
  interpreter found at build time.
- **Command line** - see :doc:`executables`.
- **CTest** - the build registers tests for both executables (see below).

Build
-----

Both executables are part of the normal CMake build and are written to the same
``bin/`` folder as ``AutoAPIFunctionDesigner_SyntaxCheck``:

.. code-block:: powershell

   cmake --preset windows-gcc-debug
   cmake --build --preset windows-gcc-debug
   ctest --test-dir build/windows-gcc-debug -R "validate_afs_cli|codegen_1"

- A Python 3.9 - 3.14 interpreter with ``venv`` is required (PyInstaller 6.16 does not
  support 3.15). On Windows, CMake finds it through the ``py`` launcher. MSYS2 Python
  is not suitable because it cannot install the required packages.
- ``-DAFD_TOOL_PYTHON=<path>`` selects the interpreter explicitly.
- ``-DAFD_BUILD_PYTHON_TOOLS=OFF`` skips both executables.
- The first build creates a private virtual environment in
  ``<build>/python_tools_build`` and needs internet access for ``pip``. Later builds
  rerun PyInstaller only when the Python sources or templates changed.

Without building, the scripts can be run directly:

.. code-block:: powershell

   cd function_designer/tools
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python validate_afs.py ..\examples\speed_hazard_detection.afs
   python generate_adapter.py ..\examples\speed_hazard_detection.afs --language cpp

The CTest tests check:

- validation of a valid and of an invalid example, a missing file, and ``--help``;
- generation of the C++ Function API and the generated folder layout (only the api
  header and the enums file are created);
- that the generated C++ header compiles (``-Wall -Wextra -Wpedantic -Werror``,
  GCC and Clang only);
- that generation is aborted for an invalid ``.afs`` file.
