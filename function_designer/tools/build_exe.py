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
# build_exe.py
#
# Freezes one of the command-line scripts (validate_afs.py, generate_adapter.py)
# into a stand-alone executable with PyInstaller. It is called by CMake (targets
# AutoAPIFunctionDesigner_ValidateAFS and AutoAPIFunctionDesigner_CodeGen_1, part
# of the normal build) but can also be run by hand:
#
#   python build_exe.py --script validate_afs.py --name AutoAPIFunctionDesigner_ValidateAFS \
#                       --output-dir <dir> [--work-dir <dir>]
#
# The interpreter that runs this script is used to create a private virtual
# environment in <work-dir>, so nothing is installed into the system Python.
# Supported interpreters: Python 3.9 - 3.14 (PyInstaller 6.16 limit).

import argparse
import os
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent


def _run(cmd) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a command-line executable from a tools script.")
    parser.add_argument("--script", required=True,
                        help="Script in the tools directory, e.g. validate_afs.py.")
    parser.add_argument("--name", required=True, help="Name of the executable (without suffix).")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Directory that receives the executable.")
    parser.add_argument("--work-dir", type=Path, default=TOOLS_DIR / "build_pyinstaller",
                        help="Directory for the virtual environment and PyInstaller files.")
    args = parser.parse_args()

    if not ((3, 9) <= sys.version_info[:2] < (3, 15)):
        print(f"ERROR: Python {sys.version_info.major}.{sys.version_info.minor} is not "
              "supported (need 3.9 - 3.14).", file=sys.stderr)
        return 1

    output_dir = args.output_dir.resolve()
    work_dir = args.work_dir.resolve()
    venv_dir = work_dir / "venv"
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    bin_dir = "Scripts" if os.name == "nt" else "bin"
    venv_python = venv_dir / bin_dir / ("python.exe" if os.name == "nt" else "python")
    if not venv_python.exists():
        _run([sys.executable, "-m", "venv", venv_dir])

    _run([venv_python, "-m", "pip", "install", "--disable-pip-version-check",
          "-r", TOOLS_DIR / "requirements-build.txt"])

    # Each executable gets its own PyInstaller work area; the venv is shared.
    pyi_dir = work_dir / "pyinstaller" / args.name
    _run([venv_python, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
          "--name", args.name,
          "--distpath", output_dir,
          "--workpath", pyi_dir,
          "--specpath", pyi_dir,
          "--paths", TOOLS_DIR,
          "--add-data", f"{TOOLS_DIR / 'templates'}{os.pathsep}templates",
          TOOLS_DIR / args.script])
    return 0


if __name__ == "__main__":
    sys.exit(main())
