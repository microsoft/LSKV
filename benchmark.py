#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from subprocess import Popen

from dataclasses import asdict, dataclass
import argparse
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


def wait_for_port(port, tries=60) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for i in range(0, tries):
        try:
            s.connect(("127.0.0.1", port))
            logging.info(f"finished waiting for port ({port}) to be open, try {i}")
            time.sleep(1)
            return True
        except:
            logging.info(f"waiting for port ({port}) to be open, try {i}")
            time.sleep(1)
    logging.error(f"took too long waiting for port {port} ({tries}s)")
    return False


def wait_for_file(file: str, tries=60) -> bool:
    for i in range(0, tries):
        if os.path.exists(file):
            logging.info(f"finished waiting for file ({file}) to exist, try {i}")
            return True
        logging.info(f"waiting for file ({file}) to exist, try {i}")
        time.sleep(1)
    logging.error(f"took too long waiting for file {file} ({tries}s)")
    return False


@dataclass
class Config:
    name: str
    port: int
    tls: bool
    sgx: bool
    worker_threads: int

    def to_str(self) -> str:
        d = asdict(self)
        s = []
        for k, v in d.items():
            s.append(f"{k}={v}")
        return ",".join(s)


class Store(abc.ABC):
    def __init__(self, bench_dir: str, config: Config):
        self.config = config
        self.bench_dir = bench_dir

    @abc.abstractmethod
    def spawn(self) -> Popen:
        raise NotImplemented

    @abc.abstractmethod
    def bench(self, _bench_cmd: List[str]):
        raise NotImplemented

    def wait_for_ready(self):
        wait_for_port(self.config.port)

    def output_dir(self) -> str:
        d = os.path.join(self.bench_dir, self.config.to_str())
        if not os.path.exists(d):
            logging.info(f"creating output dir: {d}")
            os.makedirs(d)
        return d

    def cleanup(self):
        # no cleanup for the base class to do and not a required method
        pass


class EtcdStore(Store):
    def spawn(self) -> Popen:
        logging.info(f"spawning {self.config.to_str()}")
        client_urls = f"{self.scheme()}://127.0.0.1:{self.config.port}"
        with open(os.path.join(self.output_dir(), "node.out"), "w") as out:
            with open(os.path.join(self.output_dir(), "node.err"), "w") as err:
                etcd_cmd = [
                    "bin/etcd",
                    "--listen-client-urls",
                    client_urls,
                    "--advertise-client-urls",
                    client_urls,
                ]
                if self.config.tls:
                    etcd_cmd += [
                        "--cert-file",
                        "certs/server.pem",
                        "--key-file",
                        "certs/server-key.pem",
                        "--trusted-ca-file",
                        "certs/ca.pem",
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
                    f"{self.scheme()}://127.0.0.1:{self.config.port}",
                ]
                if self.config.tls:
                    bench += [
                        "--cacert",
                        "certs/ca.pem",
                        "--cert",
                        "certs/client.pem",
                        "--key",
                        "certs/client-key.pem",
                    ]
                bench += bench_cmd
                p = Popen(bench, stdout=out, stderr=err)
                return p, timings_file

    def scheme(self) -> str:
        if self.config.tls:
            return "https"
        else:
            return "http"

    def cleanup(self):
        shutil.rmtree("default.etcd", ignore_errors=True)


class LSKVStore(Store):
    def __init__(self, bench_dir: str, port: int, sgx: bool):
        Store.__init__(self, bench_dir, port)
        self.sgx = sgx

    def spawn(self) -> Popen:
        logging.info(f"spawning {self.config.to_str()}")
        with open(os.path.join(self.output_dir(), "node.out"), "w") as out:
            with open(os.path.join(self.output_dir(), "node.err"), "w") as err:
                libargs = ["build/liblskv.virtual.so"]
                if self.config.sgx:
                    libargs = ["build/liblskv.enclave.so.signed", "-e", "release"]
                kvs_cmd = (
                    ["/opt/ccf/bin/sandbox.sh", "-p"]
                    + libargs
                    + [
                        "--worker-threads",
                        str(self.config.worker_threads),
                        "--workspace",
                        self.workspace(),
                        "--node",
                        f"local://127.0.0.1:{self.config.port}",
                        "--verbose",
                        "--http2",
                    ]
                )
                return Popen(kvs_cmd, stdout=out, stderr=err)

    def workspace(self):
        return os.path.join(os.getcwd(), self.output_dir(), "workspace")

    def wait_for_ready(self):
        def show_logs():
            out = "\n".join(
                open(os.path.join(self.output_dir(), "node.out"), "r").readlines()
            )
            print("node.out: ", out)
            print()
            err = "\n".join(
                open(os.path.join(self.output_dir(), "node.err"), "r").readlines()
            )
            print("node.err: ", err)

        if not wait_for_port(self.config.port):
            show_logs()
            return
        if not wait_for_file(
            os.path.join(self.workspace(), "sandbox_common", "user0_cert.pem")
        ):
            show_logs()
            return

    def bench(self, bench_cmd: List[str]) -> Tuple[Popen, str]:
        with open(os.path.join(self.output_dir(), "bench.out"), "w") as out:
            with open(os.path.join(self.output_dir(), "bench.err"), "w") as err:
                timings_file = os.path.join(self.output_dir(), "timings.csv")
                bench_cmd = ["--csv-file", timings_file] + bench_cmd
                bench = [
                    "bin/benchmark",
                    "--endpoints",
                    f"https://127.0.0.1:{self.config.port}",
                    "--cacert",
                    f"{self.workspace()}/sandbox_common/service_cert.pem",
                    "--cert",
                    f"{self.workspace()}/sandbox_common/user0_cert.pem",
                    "--key",
                    f"{self.workspace()}/sandbox_common/user0_privk.pem",
                ] + bench_cmd
                p = Popen(bench, stdout=out, stderr=err)
                return p, timings_file

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

    logging.info(f"starting benchmark for {store.config.to_str()}")
    bench_process, timings_file = store.bench(bench_cmd)
    wait_with_timeout(bench_process)
    logging.info(f"stopping benchmark for {store.config.to_str()}")

    proc.terminate()
    proc.wait()
    logging.info(f"stopped {store.config.to_str()}")

    store.cleanup()

    return timings_file


def run_metrics(name: str, cmd: str, file: str):
    df = pd.read_csv(file)

    start = df["start_micros"].min()
    end = df["end_micros"].max()
    count = df["start_micros"].count()
    total = (end - start) / 10**6
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--sgx", type=bool)

    args = parser.parse_args()

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

        # plain
        for tls in [False, True]:
            etcd_config = Config("etcd", port, tls, sgx=False, worker_threads=0)
            store = EtcdStore(d, etcd_config)
            timings_file = run_benchmark(store, bench_cmd)
            run_metrics(store.config.to_str(), bench_cmd[0], timings_file)

        for worker_threads in [0, 1, 2, 3]:
            lskv_config = Config(
                "lskv", port, tls=True, sgx=False, worker_threads=worker_threads
            )
            # virtual
            store = LSKVStore(d, lskv_config)
            timings_file = run_benchmark(store, bench_cmd)
            run_metrics(store.config.to_str(), bench_cmd[0], timings_file)

            # sgx
            if args.sgx:
                lskv_config.sgx = True
                store = LSKVStore(d, lskv_config)
                timings_file = run_benchmark(store, bench_cmd)
                run_metrics(store.config.to_str(), bench_cmd[0], timings_file)

    with cimetrics.upload.metrics():
        pass


if __name__ == "__main__":
    main()
