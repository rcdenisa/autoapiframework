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
# afs_common.py
#
# Small helpers shared by the command-line tools
# AutoAPIFunctionDesigner_ValidateAFS (validate_afs.py) and
# AutoAPIFunctionDesigner_CodeGen_1 (generate_adapter.py).

import argparse
import sys
from pathlib import Path

VERSION = "0.1.0"

# Exit codes shared by both tools.
EXIT_OK = 0
EXIT_FAILED = 1   # validation or generation failed
EXIT_USAGE = 2    # wrong arguments, file not found

# Keeps the line breaks of the description/epilog in --help.
HelpFormatter = argparse.RawDescriptionHelpFormatter


def configure_console() -> None:
    """Make printing robust when the output is redirected (e.g. read by the GUI):
    characters that the console code page cannot encode are replaced, not raised."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def exe_dir() -> Path:
    """Directory of the executable (or of the scripts when run with Python)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_afs_path(path: Path) -> Path:
    """Same lookup as AutoAPIFunctionDesigner_SyntaxCheck: the given path first,
    then relative to the executable (the build copies the example .afs files there)."""
    if path.exists():
        return path
    beside_exe = exe_dir() / path
    return beside_exe if beside_exe.exists() else path


def parse_args(parser: argparse.ArgumentParser, argv=None):
    """parse_args() that returns (namespace, exit_code). exit_code is None when
    parsing succeeded; --help gives EXIT_OK, wrong arguments give EXIT_USAGE."""
    try:
        return parser.parse_args(argv), None
    except SystemExit as exc:
        return None, (EXIT_OK if exc.code in (None, 0) else EXIT_USAGE)
