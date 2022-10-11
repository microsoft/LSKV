#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import abc
import argparse
import logging
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from subprocess import Popen
from typing import List, Tuple

import cimetrics.upload
import pandas as pd

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)


@dataclass
class Config:
    name: str
    port: int
    tls: bool
    sgx: bool
    worker_threads: int
    clients: int
    connections: int
    prefill_num_keys: int
    prefill_value_size: int
    # requests per second limit
    rate: int
    # total number of requests to execute
    total: int = field(init=False)

    def __post_init__(self):
        # this is based off the rate so calculate it once we know that.
        self.total = self.calculate_total()

    def to_str(self) -> str:
        d = asdict(self)
        s = []
        for k, v in d.items():
            s.append(f"{k}={v}")
        return ",".join(s)

    def benchmark_cmd(self, scenario_args: List[str]) -> str:
        bench = [
            "bin/benchmark",
            "--endpoints",
            f"{self.scheme()}://127.0.0.1:{self.port}",
            "--clients",
            str(self.clients),
            "--conns",
            str(self.connections),
        ]
        bench += scenario_args
        bench += ["--rate", str(self.rate), "--total", str(self.total)]
        return bench

    def scheme(self) -> str:
        if self.tls:
            return "https"
        else:
            return "http"

    def calculate_total(self) -> int:
        # want runs to take 60 seconds if they can handle the rate
        desired_duration_s = 60
        # default to 100,000 requests per second (things can time out)
        rate = self.rate if self.rate > 0 else 100_000
        total = desired_duration_s * rate
        return total


class Store(abc.ABC):
    def __init__(self, bench_dir: str, config: Config):
        self.config = config
        self.bench_dir = bench_dir

    def __enter__(self):
        self.proc = self.spawn()

    def __exit__(self, ex_type, ex_value, ex_traceback) -> bool:
        self.proc.terminate()
        self.proc.wait()
        logging.info(f"stopped {self.config.to_str()}")

        self.cleanup()
        return False

    @abc.abstractmethod
    def spawn(self) -> Popen:
        raise NotImplemented

    def bench(self, bench_cmd: List[str]) -> Tuple[Popen, str]:
        with open(os.path.join(self.output_dir(), "bench.out"), "w") as out:
            with open(os.path.join(self.output_dir(), "bench.err"), "w") as err:
                timings_file = os.path.join(self.output_dir(), "timings.csv")
                bench_scenario = ["--csv-file", timings_file]
                if self.config.tls:
                    bench_scenario += [
                        "--cacert",
                        self.cacert(),
                        "--cert",
                        self.cert(),
                        "--key",
                        self.key(),
                    ]
                bench_scenario += bench_cmd
                bench = self.config.benchmark_cmd(bench_scenario)
                p = Popen(bench, stdout=out, stderr=err)
                return p, timings_file

    def wait_for_ready(self):
        self._wait_for_ready(self.config.port)

    def _wait_for_ready(self, port: int, tries=60) -> bool:
        c = self.client()
        for i in range(0, tries):
            logging.debug(f"running ready check with cmd {c}")
            p = Popen(c + ["get", "missing key"])
            if p.wait() == 0:
                logging.info(f"finished waiting for port ({port}) to be open, try {i}")
                return True
            else:
                logging.info(f"waiting for port ({port}) to be open, try {i}")
                time.sleep(1)
        logging.error(f"took too long waiting for port {port} ({tries}s)")
        return False

    def output_dir(self) -> str:
        d = os.path.join(self.bench_dir, self.config.to_str())
        if not os.path.exists(d):
            logging.info(f"creating output dir: {d}")
            os.makedirs(d)
        return d

    def cleanup(self):
        # no cleanup for the base class to do and not a required method
        pass

    # get the etcd client for this datastore
    @abc.abstractmethod
    def client(self) -> List[str]:
        raise NotImplemented


class EtcdStore(Store):
    def spawn(self) -> Popen:
        logging.info(f"spawning {self.config.to_str()}")
        client_urls = f"{self.config.scheme()}://127.0.0.1:{self.config.port}"
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

    def cacert(self) -> str:
        return "certs/ca.pem"

    def cert(self) -> str:
        return "certs/client.pem"

    def key(self) -> str:
        return "certs/client-key.pem"

    def cleanup(self):
        shutil.rmtree("default.etcd", ignore_errors=True)

    def client(self) -> List[str]:
        return [
            "bin/etcdctl",
            "--endpoints",
            f"{self.config.scheme()}://127.0.0.1:{self.config.port}",
            "--cacert",
            "certs/ca.pem",
            "--cert",
            "certs/client.pem",
            "--key",
            "certs/client-key.pem",
        ]


class LSKVStore(Store):
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

    def cacert(self) -> str:
        return f"{self.workspace()}/sandbox_common/service_cert.pem"

    def cert(self) -> str:
        return f"{self.workspace()}/sandbox_common/user0_cert.pem"

    def key(self) -> str:
        return f"{self.workspace()}/sandbox_common/user0_privk.pem"

    def client(self) -> List[str]:
        return [
            "bin/etcdctl",
            "--endpoints",
            f"{self.config.scheme()}://127.0.0.1:{self.config.port}",
            "--cacert",
            f"{self.workspace()}/sandbox_common/service_cert.pem",
            "--cert",
            f"{self.workspace()}/sandbox_common/user0_cert.pem",
            "--key",
            f"{self.workspace()}/sandbox_common/user0_privk.pem",
        ]


def wait_with_timeout(process: Popen, duration_seconds=90):
    for i in range(0, duration_seconds):
        res = process.poll()
        if res is None:
            # process still running
            logging.debug(f"waiting for process to complete, try {i}")
            time.sleep(1)
        else:
            # process finished
            if res == 0:
                logging.info(
                    f"process completed successfully within timeout (took {i}s)"
                )
            else:
                logging.error(f"process failed within timeout (took {i}s): code {res}")
            return

    # didn't finish in time
    logging.error(f"killing process after timeout of {duration_seconds}s")
    process.kill()
    process.wait()
    return


def prefill_datastore(store: Store, start: int, end: int):
    time.sleep(1)
    client = store.client()
    i = 0
    num_keys = store.config.prefill_num_keys
    value_size = store.config.prefill_value_size
    logging.info(f"prefilling {num_keys} keys")
    end_size = len(str(end))
    if num_keys:
        for k in range(start, end, (end - start) // num_keys):
            i += 1
            key = str(k).zfill(end_size)
            value = "v" * value_size
            logging.debug(f"prefilling {key}")
            p = Popen(
                client + ["put", key, value],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if p.wait() != 0:
                raise Exception("failed to fill datastore")
    logging.info(f"prefilled {i} keys")


def run_benchmark(store, bench_cmd: List[str]) -> str:
    with store:
        store.wait_for_ready()

        if bench_cmd[0] == "range":
            # need to prefill the store with data for it to get
            start = int(bench_cmd[1])
            end = int(bench_cmd[2])
            logging.info(
                f"prefilling datastore with {store.config.prefill_num_keys} keys in range [{start}, {end})"
            )
            prefill_datastore(store, start, end)

        logging.info(f"starting benchmark for {store.config.to_str()}")
        bench_process, timings_file = store.bench(bench_cmd)
        wait_with_timeout(bench_process)
        logging.info(f"stopping benchmark for {store.config.to_str()}")

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


# only run multiple things for prefill_num_keys when it is actually a range bench
def get_prefill_num_keys(bench_cmd: List[str], num_keys: List[int]) -> List[int]:
    if bench_cmd[0] == "range":
        return num_keys
    else:
        return [0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sgx", type=bool)
    parser.add_argument("--no-tls", type=bool)
    parser.add_argument("--worker-threads", action="extend", nargs="+", type=int)
    parser.add_argument("--clients", action="extend", nargs="+", type=int)
    parser.add_argument("--connections", action="extend", nargs="+", type=int)
    parser.add_argument(
        "--bench-cmds", action="extend", nargs="+", type=str, default=[]
    )
    parser.add_argument(
        "--prefill-num-keys",
        action="extend",
        nargs="+",
        type=int,
        default=[],
        help="number of keys to fill datastore with before executing range benchmarks (between 0 and 1000)",
    )
    parser.add_argument(
        "--prefill-value-size",
        action="extend",
        nargs="+",
        type=int,
        default=[],
        help="size of the values (in bytes) to use in prefilling for range queries",
    )
    parser.add_argument(
        "--rate",
        action="extend",
        nargs="+",
        type=int,
        default=[],
        help="Maximum requests per second (0 is no limit)",
    )

    args = parser.parse_args()

    # set default if not set
    if not args.worker_threads:
        args.worker_threads = [0]
    if not args.clients:
        args.clients = [1]
    if not args.connections:
        args.connections = [1]
    if not args.prefill_num_keys:
        args.prefill_num_keys = [10]
    if not args.prefill_value_size:
        args.prefill_value_size = [10]
    if not args.rate:
        args.rate = [0]

    args.bench_cmds = [s.split() for s in args.bench_cmds]
    if not args.bench_cmds:
        args.bench_cmds = [
            ["put"],
            ["range", "0000", "1000"],
            ["txn-put"],
            ["txn-mixed", "txn-mixed-key"],
        ]

    bench_dir = "bench"
    port = 8000

    # make the bench directory
    shutil.rmtree(bench_dir, ignore_errors=True)
    os.makedirs(bench_dir)

    for bench_cmd in args.bench_cmds:
        logging.info(f"benching with extra args {bench_cmd}")

        bench_cmd_string = "_".join(bench_cmd)
        d = os.path.join(bench_dir, bench_cmd_string)
        os.makedirs(d)

        for clients in args.clients:
            for conns in args.connections:
                for prefill_num_keys in get_prefill_num_keys(
                    bench_cmd, args.prefill_num_keys
                ):
                    for prefill_value_size in get_prefill_num_keys(
                        bench_cmd, args.prefill_value_size
                    ):
                        for rate in args.rate:
                            if args.no_tls:
                                etcd_config = Config(
                                    "etcd",
                                    port,
                                    tls=False,
                                    sgx=False,
                                    worker_threads=0,
                                    clients=clients,
                                    connections=conns,
                                    prefill_num_keys=prefill_num_keys,
                                    prefill_value_size=prefill_value_size,
                                    rate=rate,
                                )
                                store = EtcdStore(d, etcd_config)
                                timings_file = run_benchmark(store, bench_cmd)
                                run_metrics(
                                    store.config.to_str(), bench_cmd[0], timings_file
                                )

                            etcd_config = Config(
                                "etcd",
                                port,
                                tls=True,
                                sgx=False,
                                worker_threads=0,
                                clients=clients,
                                connections=conns,
                                prefill_num_keys=prefill_num_keys,
                                prefill_value_size=prefill_value_size,
                                rate=rate,
                            )
                            store = EtcdStore(d, etcd_config)
                            timings_file = run_benchmark(store, bench_cmd)
                            run_metrics(
                                store.config.to_str(), bench_cmd[0], timings_file
                            )

                            for worker_threads in args.worker_threads:
                                lskv_config = Config(
                                    "lskv",
                                    port,
                                    tls=True,
                                    sgx=False,
                                    worker_threads=worker_threads,
                                    clients=clients,
                                    connections=conns,
                                    prefill_num_keys=prefill_num_keys,
                                    prefill_value_size=prefill_value_size,
                                    rate=rate,
                                )
                                # virtual
                                store = LSKVStore(d, lskv_config)
                                timings_file = run_benchmark(store, bench_cmd)
                                run_metrics(
                                    store.config.to_str(), bench_cmd[0], timings_file
                                )

                                # sgx
                                if args.sgx:
                                    lskv_config.sgx = True
                                    store = LSKVStore(d, lskv_config)
                                    timings_file = run_benchmark(store, bench_cmd)
                                    run_metrics(
                                        store.config.to_str(),
                                        bench_cmd[0],
                                        timings_file,
                                    )

    with cimetrics.upload.metrics():
        pass


if __name__ == "__main__":
    main()
