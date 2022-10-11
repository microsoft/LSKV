# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""
Script to check that source files have license headers.
"""

import os
import sys
import subprocess

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


def has_notice(path, prefixes):
    """
    Check that the given file has a notice.
    """
    with open(path, "r", encoding="utf-8") as file:
        text = file.read()
        for prefix in prefixes:
            if text.startswith(prefix):
                return True
    return False


def is_src(name):
    """
    Check whether the file is a source file based on the extension.
    """
    for suffix in [".c", ".cpp", ".h", ".hpp", ".py", ".sh", ".cmake"]:
        if name.endswith(suffix):
            return True
    return False


def submodules():
    """
    Get the paths of submodules in the repo.
    """
    res = subprocess.run(
        ["git", "submodule", "status"], capture_output=True, check=True
    )
    return [
        line.strip().split(" ")[1]
        for line in res.stdout.decode().split(os.linesep)
        if line
    ]


def gitignored(path):
    """
    Check if the path is ignored by git.
    """
    res = subprocess.run(
        ["git", "check-ignore", path], capture_output=True, check=False
    )
    return res.returncode == 0  # Returns 0 for files which _are_ ignored


def check_repo():
    """
    Check whether the repo's sources conform to the license headers requirement.
    """
    missing = []
    excluded = [
        "3rdparty",
        ".git",
        "build",
        "env",
        ".venv",
        ".venv_ccf_sandbox",
    ] + submodules()
    for root, dirs, files in os.walk("."):
        for edir in excluded:
            if edir in dirs:
                dirs.remove(edir)
        for name in files:
            if name.startswith("."):
                continue
            if is_src(name):
                path = os.path.join(root, name)
                if not gitignored(path):
                    if not has_notice(path, PREFIXES_CCF):
                        missing.append(path)
    return missing


if __name__ == "__main__":
    missing_paths = check_repo()
    for missing_path in missing_paths:
        print(f"Copyright notice missing from {missing_path}")
    sys.exit(len(missing_paths))
