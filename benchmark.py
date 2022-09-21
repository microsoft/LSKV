#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from subprocess import Popen
import sys
import time
import socket
from typing import List

ETCD = "etcd"
CCF_KVS = "ccf_kvs"

ETCD_BENCH_CMD = ["bin/benchmark", "--endpoints", "http://127.0.0.1:8000"]
CCF_KVS_BENCH_CMD = ["bin/benchmark", "--endpoints", "https://127.0.0.1:8000", "--cacert", "workspace/sandbox_common/service_cert.pem", "--cert", "workspace/sandbox_common/user0_cert.pem", "--key", "workspace/sandbox_common/user0_privk.pem", "put"]

def wait_for_port(port=8000):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    i = 0
    while True:
        try:
            s.connect(("127.0.0.1", port))
            break
        except:
            i += 1
            time.sleep(1)
            print(f"failed to connect {i}")
    time.sleep(1)
    print(f"connected to port {port}")

class Store:
    def spawn(self)->Popen:
        raise Exception("unimplemented")

    def bench(self, _bench_cmd:List[str]):
        raise Exception("unimplemented")

class EtcdStore:
    def spawn(self)->Popen:
        client_urls = "http://127.0.0.1:8000"
        return Popen(["bin/etcd", "--listen-client-urls", client_urls, "--advertise-client-urls", client_urls], stdout=sys.stdout, stderr=sys.stderr)

    def bench(self, bench_cmd:List[str]):
        p = Popen(ETCD_BENCH_CMD+bench_cmd, stdout=sys.stdout, stderr=sys.stderr)
        p.wait()

class CCFKVSStore:
    def spawn(self)->Popen:
        return Popen(["/opt/ccf/bin/sandbox.sh", "-p", "build/libccf_kvs.virtual.so", "--http2"], stdout=sys.stdout, stderr=sys.stderr)

    def bench(self, bench_cmd:List[str]):
        p = Popen(CCF_KVS_BENCH_CMD+bench_cmd, stdout=sys.stdout, stderr=sys.stderr)
        p.wait()

def run_benchmark(store, bench_cmd:List[str]):
    proc = store.spawn()

    wait_for_port()

    print("starting benchmark")
    store.bench(bench_cmd)
    print("stopping benchmark")

    proc.terminate()
    proc.wait()

def main():
    bench_cmd = ["put"]
    run_benchmark(EtcdStore(), bench_cmd)

    run_benchmark(CCFKVSStore(), bench_cmd)

if __name__ == "__main__":
    main()
