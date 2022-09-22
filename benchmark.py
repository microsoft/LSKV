#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from subprocess import Popen
import shutil
import time
import cimetrics.upload
import logging
import pandas as pd
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
                # TODO(#41): enable tls connection for etcd
                etcd_cmd = [
                    "bin/etcd",
                    "--listen-client-urls",
                    client_urls,
                    "--advertise-client-urls",
                    client_urls,
                ]
                return Popen(etcd_cmd, stdout=out, stderr=err)

    def bench(self, bench_cmd: List[str]) -> str:
        with open(os.path.join(self.bench_dir, "etcd_bench.out"), "w") as out:
            with open(os.path.join(self.bench_dir, "etcd_bench.err"), "w") as err:
                timings_file = os.path.join(self.bench_dir, "etcd_timings.csv")
                bench_cmd = ["--csv-file", timings_file] + bench_cmd
                bench = [
                    "bin/benchmark",
                    "--endpoints",
                    f"http://127.0.0.1:{self.port}",
                ] + bench_cmd
                p = Popen(bench, stdout=out, stderr=err)
                p.wait()
                return timings_file

    def name(self) -> str:
        return "etcd"


class CCFKVSStore(Store):
    def spawn(self) -> Popen:
        logging.info(f"spawning {self.name()}")
        with open(os.path.join(self.bench_dir, "ccf_kvs.out"), "w") as out:
            with open(os.path.join(self.bench_dir, "ccf_kvs.err"), "w") as err:
                kvs_cmd = [
                    "/opt/ccf/bin/sandbox.sh",
                    "-p",
                    "build/libccf_kvs.virtual.so",
                    "--http2",
                ]
                return Popen(kvs_cmd, stdout=out, stderr=err)

    def bench(self, bench_cmd: List[str]) -> str:
        with open(os.path.join(self.bench_dir, "ccf_kvs_bench.out"), "w") as out:
            with open(os.path.join(self.bench_dir, "ccf_kvs_bench.err"), "w") as err:
                timings_file = os.path.join(self.bench_dir, "ccf_kvs_timings.csv")
                bench_cmd = ["--csv-file", timings_file] + bench_cmd
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
                return timings_file

    def name(self) -> str:
        return "ccf_kvs"


def run_benchmark(store, bench_cmd: List[str]) -> str:
    proc = store.spawn()

    store.wait()

    logging.info(f"starting benchmark for {store.name()}")
    timings_file = store.bench(bench_cmd)
    logging.info(f"stopping benchmark for {store.name()}")

    proc.terminate()
    proc.wait()
    logging.info(f"stopped {store.name()}")
    return timings_file


def run_metrics(name: str, cmd: str, file: str):
    df = pd.read_csv(file)

    start = df["start_micros"].min()
    end = df["end_micros"].max()
    count = df["start_micros"].count()
    thput = count / ((end - start) / 10 ** 6)

    latencies = (df["end_micros"] - df["start_micros"]) / 1000
    latency_p50 = latencies.quantile(0.5)
    latency_p90 = latencies.quantile(0.9)
    latency_p99 = latencies.quantile(0.99)
    latency_p999 = latencies.quantile(0.999)

    print(f"throughput (req/s): {thput}")
    print(f"  p50 latency (ms): {latency_p50}")
    print(f"  p90 latency (ms): {latency_p90}")
    print(f"  p99 latency (ms): {latency_p99}")
    print(f"p99.9 latency (ms): {latency_p999}")

    group = f"{name}_{cmd}"
    with cimetrics.upload.metrics(complete=False) as metrics:
        metrics.put(f"throughput (req/s)^", thput, group=group)
        metrics.put(f"latency p50 (ms)", latency_p50, group=group)
        metrics.put(f"latency p90 (ms)", latency_p90, group=group)
        metrics.put(f"latency p99 (ms)", latency_p99, group=group)
        metrics.put(f"latency p99.9 (ms)", latency_p999, group=group)


def main():
    bench_dir = "bench"
    port = 8000

    # make the bench directory
    shutil.rmtree(bench_dir)
    os.makedirs(bench_dir)

    # TODO(#40): write a kv into the store for the range query benchmark
    bench_cmds = [
        ["put"],
        ["range", "range-key"],
        ["txn-put"],
        ["txn-mixed", "txn-mixed-key"],
    ]
    for bench_cmd in bench_cmds:
        logging.info(f"benching with extra args {bench_cmd}")

        bench_cmd_string = "_".join(bench_cmd)
        d = os.path.join(bench_dir, bench_cmd_string)
        os.makedirs(d)

        store = EtcdStore(d, port)
        timings_file = run_benchmark(store, bench_cmd)
        run_metrics(store.name(), bench_cmd_string, timings_file)

        store = CCFKVSStore(d, port)
        timings_file = run_benchmark(store, bench_cmd)
        run_metrics(store.name(), bench_cmd_string, timings_file)

    with cimetrics.upload.metrics():
        pass


if __name__ == "__main__":
    main()
