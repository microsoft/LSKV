#!/usr/bin/env sh

parallelism=1

test_dir=$(realpath $(dirname $0))
ccf_kvs_dir=$(realpath $test_dir/../../..)

echo "changing dir to $test_dir"
cd $test_dir

cmd="env ETCD_VERIFY=all CCF_KVS_DIR=$ccf_kvs_dir go test --tags=integration --timeout=10m -p=$parallelism -run=TestKV $test_dir/common/... $@"
echo $cmd
$cmd
