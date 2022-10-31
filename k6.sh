#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

function wait_ready() {
    res=1
    while [[ $res -ne 0 ]]; do
        echo "waiting"
        curl --cacert workspace/sandbox_common/service_cert.pem --cert workspace/sandbox_common/user0_cert.pem --key workspace/sandbox_common/user0_privk.pem https://127.0.0.1:8000/node/version
        res=$?
        sleep 1
    done
    echo "ready"
}

function run_and_load() {
    echo "running $2"
    rm -rf workspace
    make "$1" &
    process_id=$!
    echo "launched sandbox, waiting for it to be ready"
    wait_ready
    echo "waiting to let it relax"
    sleep 1
    echo "running k6"
    k6 run benchmark/k6.js > "$2".out 2>&1
    echo "killing process"
    kill $process_id
    pkill cchost
    echo "waiting for process to stop"
    sleep 1
}

run_and_load "run-virtual" "http2_safe"

run_and_load "run-virtual-http1" "http1_safe"

run_and_load "run-virtual-unsafe" "http2_unsafe"

run_and_load "run-virtual-unsafe-http1" "http1_unsafe"