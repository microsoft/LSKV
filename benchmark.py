#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from subprocess import Popen
import abc
import shutil
import time
import cimetrics.upload
import logging
import pandas as pd
import socket
import os
from typing import List, Tuple

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)


def wait_for_port(port, tries=60):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for i in range(0, tries):
        try:
            s.connect(("127.0.0.1", port))
            logging.info(f"finished waiting for port ({port}) to be open, try {i}")
            time.sleep(1)
            return
        except:
            logging.info(f"waiting for port ({port}) to be open, try {i}")
            time.sleep(1)
    logging.error(f"took too long waiting for port {port} ({tries}s)")


def wait_for_file(file: str, tries=60):
    for i in range(0, tries):
        if os.path.exists(file):
            logging.info(f"finished waiting for file ({file}) to exist, try {i}")
            return
        logging.info(f"waiting for file ({file}) to exist, try {i}")
        time.sleep(1)
    logging.error(f"took too long waiting for file {file} ({tries}s)")


class Store(abc.ABC):
    def __init__(self, bench_dir: str, port: int):
        self.bench_dir = bench_dir
        self.port = port

    @abc.abstractmethod
    def spawn(self) -> Popen:
        raise NotImplemented

    @abc.abstractmethod
    def bench(self, _bench_cmd: List[str]):
        raise NotImplemented

    def wait_for_ready(self):
        wait_for_port(self.port)

    @abc.abstractmethod
    def name(self):
        raise NotImplemented

    def output_dir(self) -> str:
        d = os.path.join(self.bench_dir, self.name())
        if not os.path.exists(d):
            logging.info(f"creating output dir: {d}")
            os.makedirs(d)
        return d

    def cleanup(self):
        # no cleanup for the base class to do and not a required method
        pass


class EtcdStore(Store):
    def spawn(self) -> Popen:
        logging.info(f"spawning {self.name()}")
        client_urls = f"http://127.0.0.1:{self.port}"
        with open(os.path.join(self.output_dir(), "node.out"), "w") as out:
            with open(os.path.join(self.output_dir(), "node.err"), "w") as err:
                # TODO(#41): enable tls connection for etcd
                etcd_cmd = [
                    "bin/etcd",
                    "--listen-client-urls",
                    client_urls,
                    "--advertise-client-urls",
                    client_urls,
                ]
                return Popen(etcd_cmd, stdout=out, stderr=err)

    def bench(self, bench_cmd: List[str]) -> Tuple[Popen, str]:
        with open(os.path.join(self.output_dir(), "bench.out"), "w") as out:
            with open(os.path.join(self.output_dir(), "bench.err"), "w") as err:
                timings_file = os.path.join(self.output_dir(), "timings.csv")
                bench_cmd = ["--csv-file", timings_file] + bench_cmd
                bench = [
                    "bin/benchmark",
                    "--endpoints",
                    f"http://127.0.0.1:{self.port}",
                ] + bench_cmd
                p = Popen(bench, stdout=out, stderr=err)
                return p, timings_file

    def name(self) -> str:
        return "etcd-notls-virtual"

    def cleanup(self):
        shutil.rmtree("default.etcd", ignore_errors=True)


class CCFKVSStore(Store):
    def spawn(self) -> Popen:
        logging.info(f"spawning {self.name()}")
        with open(os.path.join(self.output_dir(), "node.out"), "w") as out:
            with open(os.path.join(self.output_dir(), "node.err"), "w") as err:
                kvs_cmd = [
                    "/opt/ccf/bin/sandbox.sh",
                    "-p",
                    "build/libccf_kvs.virtual.so",
                    "--node",
                    f"local://127.0.0.1:{self.port}",
                    "--verbose",
                    "--http2",
                ]
                return Popen(kvs_cmd, stdout=out, stderr=err)

    def wait_for_ready(self):
        wait_for_port(self.port)
        wait_for_file(os.path.join("workspace", "sandbox_common", "user0_cert.pem"))

    def bench(self, bench_cmd: List[str]) -> Tuple[Popen, str]:
        with open(os.path.join(self.output_dir(), "bench.out"), "w") as out:
            with open(os.path.join(self.output_dir(), "bench.err"), "w") as err:
                timings_file = os.path.join(self.output_dir(), "timings.csv")
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
                return p, timings_file

    def name(self) -> str:
        return "ccfkvs-tls-virtual"

    def cleanup(self):
        shutil.rmtree("workspace", ignore_errors=True)


def wait_with_timeout(process: Popen, duration_seconds=90):
    for i in range(0, duration_seconds):
        if process.poll() is None:
            # process still running
            logging.debug(f"waiting for process to complete, try {i}")
            time.sleep(1)
        else:
            # process finished
            logging.info(f"process completed successfully within timeout (took {i}s)")
            return

    # didn't finish in time
    logging.error(f"killing process after timeout of {duration_seconds}s")
    process.kill()
    process.wait()
    return


def run_benchmark(store, bench_cmd: List[str]) -> str:
    proc = store.spawn()

    store.wait_for_ready()

    logging.info(f"starting benchmark for {store.name()}")
    bench_process, timings_file = store.bench(bench_cmd)
    wait_with_timeout(bench_process)
    logging.info(f"stopping benchmark for {store.name()}")

    proc.terminate()
    proc.wait()
    logging.info(f"stopped {store.name()}")

    store.cleanup()

    return timings_file


def run_metrics(name: str, cmd: str, file: str):
    df = pd.read_csv(file)

    start = df["start_micros"].min()
    end = df["end_micros"].max()
    count = df["start_micros"].count()
    total = (end - start) / 10 ** 6
    thput = count / total

    latencies = (df["end_micros"] - df["start_micros"]) / 1000
    latency_p50 = latencies.quantile(0.5)
    latency_p90 = latencies.quantile(0.9)
    latency_p99 = latencies.quantile(0.99)
    latency_p999 = latencies.quantile(0.999)

    logging.info(f"             count: {count}")
    logging.info(f"         total (s): {total}")
    logging.info(f"throughput (req/s): {thput}")
    logging.info(f"  p50 latency (ms): {latency_p50}")
    logging.info(f"  p90 latency (ms): {latency_p90}")
    logging.info(f"  p99 latency (ms): {latency_p99}")
    logging.info(f"p99.9 latency (ms): {latency_p999}")

    group = name
    with cimetrics.upload.metrics(complete=False) as metrics:
        metrics.put(f"{cmd} throughput (req/s)^", thput, group=group)
        metrics.put(f"{cmd} latency p50 (ms)", latency_p50, group=group)
        metrics.put(f"{cmd} latency p90 (ms)", latency_p90, group=group)
        metrics.put(f"{cmd} latency p99 (ms)", latency_p99, group=group)
        metrics.put(f"{cmd} latency p99.9 (ms)", latency_p999, group=group)


def main():
    bench_dir = "bench"
    port = 8000

    # make the bench directory
    shutil.rmtree(bench_dir, ignore_errors=True)
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
        run_metrics(store.name(), bench_cmd[0], timings_file)

        store = CCFKVSStore(d, port)
        timings_file = run_benchmark(store, bench_cmd)
        run_metrics(store.name(), bench_cmd[0], timings_file)

    with cimetrics.upload.metrics():
        pass


if __name__ == "__main__":
    main()
