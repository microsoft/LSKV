#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from subprocess import Popen
import shutil
import time
import logging
import socket
import os
from typing import List

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

ETCD = "etcd"
CCF_KVS = "ccf_kvs"

ETCD_BENCH_CMD = ["bin/benchmark", "--endpoints", "http://127.0.0.1:8000"]
CCF_KVS_BENCH_CMD = [
    "bin/benchmark",
    "--endpoints",
    "https://127.0.0.1:8000",
    "--cacert",
    "workspace/sandbox_common/service_cert.pem",
    "--cert",
    "workspace/sandbox_common/user0_cert.pem",
    "--key",
    "workspace/sandbox_common/user0_privk.pem",
]


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
    time.sleep(1)


class Store:
    def __init__(self, bench_dir: str):
        self.bench_dir = bench_dir

    def spawn(self) -> Popen:
        raise Exception("unimplemented")

    def bench(self, _bench_cmd: List[str]):
        raise Exception("unimplemented")

    def name(self):
        raise Exception("unimplemented")


class EtcdStore(Store):
    def spawn(self) -> Popen:
        logging.info(f"spawning {self.name()}")
        client_urls = "http://127.0.0.1:8000"
        with open(os.path.join(self.bench_dir, "etcd.out"), "w") as out:
            with open(os.path.join(self.bench_dir, "etcd.err"), "w") as err:
                return Popen(
                    [
                        "bin/etcd",
                        "--listen-client-urls",
                        client_urls,
                        "--advertise-client-urls",
                        client_urls,
                    ],
                    stdout=out,
                    stderr=err,
                )

    def bench(self, bench_cmd: List[str]):
        with open(os.path.join(self.bench_dir, "etcd_bench.out"), "w") as out:
            with open(os.path.join(self.bench_dir, "etcd_bench.err"), "w") as err:
                p = Popen(ETCD_BENCH_CMD + bench_cmd, stdout=out, stderr=err)
                p.wait()

    def name(self) -> str:
        return "etcd"


class CCFKVSStore(Store):
    def spawn(self) -> Popen:
        logging.info(f"spawning {self.name()}")
        with open(os.path.join(self.bench_dir, "ccf_kvs.out"), "w") as out:
            with open(os.path.join(self.bench_dir, "ccf_kvs.err"), "w") as err:
                return Popen(
                    [
                        "/opt/ccf/bin/sandbox.sh",
                        "-p",
                        "build/libccf_kvs.virtual.so",
                        "--http2",
                    ],
                    stdout=out,
                    stderr=err,
                )

    def bench(self, bench_cmd: List[str]):
        with open(os.path.join(self.bench_dir, "ccf_kvs_bench.out"), "w") as out:
            with open(os.path.join(self.bench_dir, "ccf_kvs_bench.err"), "w") as err:
                p = Popen(CCF_KVS_BENCH_CMD + bench_cmd, stdout=out, stderr=err)
                p.wait()

    def name(self) -> str:
        return "ccf_kvs"


def run_benchmark(store, bench_cmd: List[str]):
    proc = store.spawn()

    wait_for_port()

    logging.info(f"starting benchmark for {store.name()}")
    store.bench(bench_cmd)
    logging.info(f"stopping benchmark for {store.name()}")

    proc.terminate()
    proc.wait()
    logging.info(f"stopped {store.name()}")


def main():
    bench_dir = "bench"

    # make the bench directory
    shutil.rmtree(bench_dir)
    os.makedirs(bench_dir)

    # todo: write a kv into the store for the range query benchmark
    bench_cmds = [["put"], ["range", "key"]]
    for bench_cmd in bench_cmds:
        logging.info(f"benching with extra args {bench_cmd}")

        d = os.path.join(bench_dir, "_".join(bench_cmd))
        if not os.path.exists(d):
            os.makedirs(d)

        run_benchmark(EtcdStore(d), bench_cmd)

        run_benchmark(CCFKVSStore(d), bench_cmd)


if __name__ == "__main__":
    main()
