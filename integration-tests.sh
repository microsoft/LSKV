#!/usr/bin/env sh
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

parallelism=1

build_dir=build

test_dir=$(realpath $build_dir/3rdparty/etcd/tests)
ccf_kvs_dir=$(realpath ./.)

echo "changing dir to $test_dir"
cd "$test_dir" || exit 1

cmd="env ETCD_VERIFY=all CCF_KVS_DIR=$ccf_kvs_dir VENV_DIR=$ccf_kvs_dir/.venv_ccf_sandbox go test --tags=integration --timeout=10m -p=$parallelism -run=TestKV $test_dir/common/... $*"
echo "$cmd"
$cmd
