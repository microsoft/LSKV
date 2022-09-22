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


def wait_for_port(port):
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
    def __init__(self, bench_dir: str, port: int):
        self.bench_dir = bench_dir
        self.port = port

    def spawn(self) -> Popen:
        raise Exception("unimplemented")

    def bench(self, _bench_cmd: List[str]):
        raise Exception("unimplemented")

    def wait(self):
        wait_for_port(self.port)

    def name(self):
        raise Exception("unimplemented")


class EtcdStore(Store):
    def spawn(self) -> Popen:
        logging.info(f"spawning {self.name()}")
        client_urls = f"http://127.0.0.1:{self.port}"
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
                bench_cmd = [
                    "--csv-file",
                    os.path.join(self.bench_dir, "etcd_timings.csv"),
                ] + bench_cmd
                bench = [
                    "bin/benchmark",
                    "--endpoints",
                    f"http://127.0.0.1:{self.port}",
                ] + bench_cmd
                p = Popen(bench, stdout=out, stderr=err)
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
                bench_cmd = [
                    "--csv-file",
                    os.path.join(self.bench_dir, "ccf_kvs_timings.csv"),
                ] + bench_cmd
                bench = [
                    "bin/benchmark",
                    "--endpoints",
                    f"https://127.0.0.1:{self.port}",
                    "--cacert",
                    "workspace/sandbox_common/service_cert.pem",
                    "--cert",
                    "workspace/sandbox_common/user0_cert.pem",
                    "--key",
                    "workspace/sandbox_common/user0_privk.pem",
                ] + bench_cmd
                p = Popen(bench, stdout=out, stderr=err)
                p.wait()

    def name(self) -> str:
        return "ccf_kvs"


def run_benchmark(store, bench_cmd: List[str]):
    proc = store.spawn()

    store.wait()

    logging.info(f"starting benchmark for {store.name()}")
    store.bench(bench_cmd)
    logging.info(f"stopping benchmark for {store.name()}")

    proc.terminate()
    proc.wait()
    logging.info(f"stopped {store.name()}")


def main():
    bench_dir = "bench"
    port = 8000

    # make the bench directory
    shutil.rmtree(bench_dir)
    os.makedirs(bench_dir)

    # TODO(#40): write a kv into the store for the range query benchmark
    bench_cmds = [["put"], ["range", "key"]]
    for bench_cmd in bench_cmds:
        logging.info(f"benching with extra args {bench_cmd}")

        d = os.path.join(bench_dir, "_".join(bench_cmd))
        os.makedirs(d)

        run_benchmark(EtcdStore(d, port), bench_cmd)

        run_benchmark(CCFKVSStore(d, port), bench_cmd)


if __name__ == "__main__":
    main()
