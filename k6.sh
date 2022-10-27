#!/usr/bin/env bash

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
    make $1 &
    process_id=$!
    wait_ready
    k6 run benchmark/k6.js 2>&1 > $2.out
    sleep 1
    kill $process_id
}

run_and_load "run-virtual" "http2_safe"

run_and_load "run-virtual-http1" "http1_safe"

run_and_load "run-virtual-unsafe" "http2_unsafe"

run_and_load "run-virtual-unsafe-http1" "http1_unsafe"