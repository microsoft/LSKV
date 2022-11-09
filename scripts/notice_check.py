# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""
Script to check that source files have license headers.
"""

import os
import subprocess
import sys
from typing import List

NOTICE_LINES_CCF = [
    "Copyright (c) Microsoft Corporation. All rights reserved.",
    "Licensed under the MIT License.",
]

PREFIXES_CCF = [
    os.linesep.join([prefix + " " + line for line in NOTICE_LINES_CCF])
    for prefix in ["//", "--", "#"]
]
PREFIXES_CCF.append("#!/bin/bash" + os.linesep + "#")
PREFIXES_CCF.append("#!/usr/bin/env sh" + os.linesep + "#")
PREFIXES_CCF.append("#!/usr/bin/env bash" + os.linesep + "#")
PREFIXES_CCF.append("#!/usr/bin/env python3" + os.linesep + "#")


def has_notice(path: str, prefixes: List[str]) -> bool:
    """
    Check that the given file has a notice.
    """
    with open(path, "r", encoding="utf-8") as file:
        text = file.read()
        for prefix in prefixes:
            if text.startswith(prefix):
                return True
    return False


if __name__ == "__main__":
    files = sys.argv[1:]
    missing = 0
    for file in files:
        if not has_notice(file, PREFIXES_CCF):
            missing += 1
            print(f"Copyright notice missing from {file}")
    sys.exit(missing)
