#!/usr/bin/env sh

parallelism=1

build_dir=build

test_dir=$(realpath $build_dir/3rdparty/etcd/tests)
ccf_kvs_dir=$(realpath ./.)

echo "changing dir to $test_dir"
cd $test_dir

cmd="env ETCD_VERIFY=all CCF_KVS_DIR=$ccf_kvs_dir VENV_DIR=$ccf_kvs_dir/.venv_ccf_sandbox go test --tags=integration --timeout=10m -p=$parallelism -run=TestKV $test_dir/common/... $@"
echo $cmd
$cmd
