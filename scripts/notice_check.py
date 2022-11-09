# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""
Script to check that source files have license headers.
"""

import subprocess
import sys
from typing import List

from loguru import logger

license_header = "Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the MIT License."

comment_prefixes = ["//", "#"]

def extract_potential_license(lines:List[str])->str:
    license_lines = []
    for line in lines:
        was_comment = False
        for comment_prefix in comment_prefixes:
            if line.startswith(comment_prefix):
                line = line.lstrip(comment_prefix)
                was_comment = True
        if not was_comment:
            logger.debug("stopping at line: {}", line.strip())
            return " ".join(license_lines)
        license_lines.append(line.strip())

    return " ".join(license_lines)

def has_notice(path: str) -> bool:
    """
    Check that the given file has a notice.
    """
    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        license_lines = extract_potential_license(lines)
        if license_header in license_lines:
            return True
        logger.debug("   found: {}", license_lines)
        logger.debug("expected: {}", license_header)

    return False

def git_ls_files() -> List[str]:
    excluded = [
        "3rdparty/", # these aren't ours
        "LICENSE", # don't need a license on the license
        "*.json", # can't add comments to these files
        "*.ipynb", # can't add comments to these files
        "*.md", # just documentation
        ".gitmodules", # not a source file
        ".gitignore", # not a source file
        ".dockerignore", # not a source file
        ".clang-format", # not a source file
        "proto/etcd.proto", # mostly not ours
        "proto/status.proto", # mostly not ours
        ".github/workflows", # not source files
    ]
    excluded = [f":!:{e}" for e in excluded]
    cmd = ["git", "ls-files", "--", "."] + excluded
    res = subprocess.run(cmd, check=True, capture_output=True)
    return res.stdout.decode("utf-8").strip().split("\n")

if __name__ == "__main__":
    logger.remove()
    logger.add(sink=sys.stdout, level="WARNING")

    files = git_ls_files()

    missing = 0
    for file in files:
        logger.info("Checking {}", file)
        if not has_notice(file):
            missing += 1
            logger.warning("Copyright notice missing from {}", file)
    sys.exit(missing)
