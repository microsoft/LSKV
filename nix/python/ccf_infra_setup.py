# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the Apache 2.0 License.

"""
Setup infra for ccf.
"""


from setuptools import setup  # type: ignore

PACKAGE_NAME = "infra"

with open("requirements.txt", encoding="utf-8") as f:
    requirements = f.read().splitlines()

setup(
    name=PACKAGE_NAME,
    version="2.0.0",
    description="Set of tools and utilities for the Confidential Consortium Framework (CCF)",
    url="https://github.com/microsoft/CCF/tree/main/python",
    license="Apache License 2.0",
    author="CCF Team",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
    ],
    packages=[PACKAGE_NAME],
    python_requires=">=3.8",
    install_requires=requirements,
    scripts=["start_network.py"],
)
