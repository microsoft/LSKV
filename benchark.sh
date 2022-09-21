#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

set -e

bindir=$(realpath bin)

install_benchmark() {
    ETCD_VER="v3.5.4"

    GITHUB_URL=https://github.com/etcd-io/etcd

    tmpdir=$(mktemp -d)

    git clone $GITHUB_URL $tmpdir

    cd $tmpdir

    git checkout $ETCD_VER

    go build -v ./tools/benchmark

    mkdir -p $bindir
    mv benchmark $bindir

    rm -rf $tmpdir
    cd -
}

if [ ! -f "$bindir/benchmark" ]; then
    echo "$bindir/benchmark missing, downloading and building benchmark tool"
    install_benchmark
fi

workspace_common=workspace/sandbox_common

cmd="$bindir/benchmark --endpoints=https://127.0.0.1:8000 --cacert=$workspace_common/service_cert.pem --cert=$workspace_common/user0_cert.pem --key=$workspace_common/user0_privk.pem $*"
echo "$cmd"
$cmd
