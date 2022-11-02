#!/bin/bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

set -e

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <path_to_proto_file> <output_directory>"
fi

THIS_DIR=$( dirname "${BASH_SOURCE[0]}" )
SOURCE_FILE=${1}
GENERATED_DIR=${2}

mkdir -p "${GENERATED_DIR}"

echo " -- Building ${SOURCE_FILE} into ${GENERATED_DIR}"
python3 -m grpc_tools.protoc \
        -I "${THIS_DIR}" \
        --python_out "${GENERATED_DIR}" \
        "${SOURCE_FILE}"