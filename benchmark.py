#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run benchmarks in various configurations for each defined datastore.
"""

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

import cimetrics.upload # type: ignore
import pandas as pd # type: ignore
import typing_extensions

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

# want runs to take a limited number of seconds if they can handle the rate
DESIRED_DURATION_S = 20


# pylint: disable=too-many-instance-attributes
@dataclass
class Config:
    """
    Config holds the configuration options for a given benchmark run.
    """

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
        """
        Calculate extra data based on the config.
        """
        # this is based off the rate so calculate it once we know that.
        self.total = self.calculate_total()

    def to_str(self) -> str:
        """
        Convert the config to a string.
        """
        config_dict = asdict(self)
        string_parts = []
        for k, value in config_dict.items():
            string_parts.append(f"{k}={value}")
        return ",".join(string_parts)

    def benchmark_cmd(self, scenario_args: List[str]) -> List[str]:
        """
        Return the command to run the benchmark.
        """
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
        """
        Return the scheme for the config.
        """
        if self.tls:
            return "https"
        return "http"

    def calculate_total(self) -> int:
        """
        Return the total number of requests to execute.
        """
        # default requests per second (things can time out)
        rate = self.rate if self.rate > 0 else 1_000
        total = DESIRED_DURATION_S * rate
        return total


class Store(abc.ABC):
    """
    The base store for running benchmarks against.
    """

    def __init__(self, bench_dir: str, config: Config):
        self.config = config
        self.bench_dir = bench_dir
        self.proc = None

    def __enter__(self):
        self.proc = self.spawn()

    def __exit__(
        self, ex_type, ex_value, ex_traceback
    ) -> typing_extensions.Literal[False]:
        if self.proc:
            self.proc.terminate()
            self.proc.wait()
            logging.info("stopped %s", self.config.to_str())

        self.cleanup()
        return False

    @abc.abstractmethod
    def spawn(self) -> Popen:
        """
        Spawn the datastore process.
        """
        raise NotImplementedError

    def bench(self, bench_cmd: List[str]) -> Tuple[Popen, str]:
        """
        Run the benchmark command and return the process and the timings file.
        """
        with open(
            os.path.join(self.output_dir(), "bench.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(self.output_dir(), "bench.err"), "w", encoding="utf-8"
            ) as err:
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
                # pylint: disable=consider-using-with
                proc = Popen(bench, stdout=out, stderr=err)
                return proc, timings_file

    def wait_for_ready(self):
        """
        Wait for the datastore to be ready to accept requests.
        """
        self._wait_for_ready(self.config.port)

    def _wait_for_ready(self, port: int, tries=60) -> bool:
        client = self.client()
        for i in range(0, tries):
            logging.debug("running ready check with cmd %s", client)
            # pylint: disable=consider-using-with
            proc = Popen(client + ["get", "missing key"])
            if proc.wait() == 0:
                logging.info(
                    "finished waiting for port (%d) to be open, try %d", port, i
                )
                return True
            logging.info("waiting for port (%d) to be open, try %d", port, i)
            time.sleep(1)
        logging.error("took too long waiting for port %d (%ds)", port, tries)
        return False

    def output_dir(self) -> str:
        """
        Return the output directory for this datastore.
        """
        out_dir = os.path.join(self.bench_dir, self.config.to_str())
        if not os.path.exists(out_dir):
            logging.info("creating output dir: %d", out_dir)
            os.makedirs(out_dir)
        return out_dir

    def cleanup(self):
        """
        Cleanup resources used for this datastore.
        """
        # no cleanup for the base class to do and not a required method

    @abc.abstractmethod
    def key(self) -> str:
        """
        Return the path to the key for the client certificate.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def cert(self) -> str:
        """
        Return the path to the client certificate.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def cacert(self) -> str:
        """
        Return the path to the CA certificate.
        """
        raise NotImplementedError

    # get the etcd client for this datastore
    def client(self) -> List[str]:
        """
        Get the etcdctl client command for this datastore.
        """
        return [
            "bin/etcdctl",
            "--endpoints",
            f"{self.config.scheme()}://127.0.0.1:{self.config.port}",
            "--cacert",
            self.cacert(),
            "--cert",
            self.cert(),
            "--key",
            self.key(),
        ]


class EtcdStore(Store):
    """
    A store based on etcd.
    """

    def spawn(self) -> Popen:
        logging.info("spawning %s", self.config.to_str())
        client_urls = f"{self.config.scheme()}://127.0.0.1:{self.config.port}"
        with open(
            os.path.join(self.output_dir(), "node.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(self.output_dir(), "node.err"), "w", encoding="utf-8"
            ) as err:
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
        """
        Return the path to the CA certificate.
        """
        return "certs/ca.pem"

    def cert(self) -> str:
        """
        Return the path to the client certificate.
        """
        return "certs/client.pem"

    def key(self) -> str:
        """
        Return the path to the key for the client certificate.
        """
        return "certs/client-key.pem"

    def cleanup(self):
        shutil.rmtree("default.etcd", ignore_errors=True)


class LSKVStore(Store):
    """
    A store based on LSKV.
    """

    def spawn(self) -> Popen:
        logging.info("spawning %s", self.config.to_str())
        with open(
            os.path.join(self.output_dir(), "node.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(self.output_dir(), "node.err"), "w", encoding="utf-8"
            ) as err:
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
        """
        Return the workspace directory for this store.
        """
        return os.path.join(os.getcwd(), self.output_dir(), "workspace")

    def cacert(self) -> str:
        """
        Return the path to the CA certificate.
        """
        return f"{self.workspace()}/sandbox_common/service_cert.pem"

    def cert(self) -> str:
        """
        Return the path to the client certificate.
        """
        return f"{self.workspace()}/sandbox_common/user0_cert.pem"

    def key(self) -> str:
        """
        Return the path to the key for the client certificate.
        """
        return f"{self.workspace()}/sandbox_common/user0_privk.pem"


def wait_with_timeout(process: Popen, duration_seconds=2 * DESIRED_DURATION_S):
    """
    Wait for a process to complete, but timeout after the given duration.
    """
    for i in range(0, duration_seconds):
        res = process.poll()
        if res is None:
            # process still running
            logging.info("waiting for process to complete, try %d", i)
            time.sleep(1)
        else:
            # process finished
            if res == 0:
                logging.info(
                    "process completed successfully within timeout (took %ds)", i
                )
            else:
                logging.error(
                    "process failed within timeout (took %ds): code %s", i, res
                )
            return

    # didn't finish in time
    logging.error("killing process after timeout of %ss", duration_seconds)
    process.kill()
    process.wait()
    return


def prefill_datastore(store: Store, start: int, end: int):
    """
    Fill the datastore with a range of keys.
    """
    time.sleep(1)
    client = store.client()
    i = 0
    num_keys = store.config.prefill_num_keys
    value_size = store.config.prefill_value_size
    logging.info("prefilling %d keys", num_keys)
    end_size = len(str(end))
    if num_keys:
        for k in range(start, end, (end - start) // num_keys):
            i += 1
            key = str(k).zfill(end_size)
            value = "v" * value_size
            logging.debug("prefilling %s", key)
            # pylint: disable=consider-using-with
            proc = Popen(
                client + ["put", key, value],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if proc.wait() != 0:
                raise Exception("failed to fill datastore")
    logging.info("prefilled %d keys", i)


def run_benchmark(store, bench_cmd: List[str]) -> str:
    """
    Run the benchmark for the given store with the given bench command.
    """
    with store:
        store.wait_for_ready()

        if bench_cmd[0] == "range":
            # need to prefill the store with data for it to get
            start = int(bench_cmd[1])
            end = int(bench_cmd[2])
            logging.info(
                "prefilling datastore with %d keys in range [%d, %d)",
                store.config.prefill_num_keys,
                start,
                end,
            )
            prefill_datastore(store, start, end)

        logging.info("starting benchmark for %s", store.config.to_str())
        bench_process, timings_file = store.bench(bench_cmd)
        wait_with_timeout(bench_process)
        logging.info("stopping benchmark for %s", store.config.to_str())

    return timings_file


# pylint: disable=too-many-locals
def run_metrics(name: str, cmd: str, file: str):
    """
    Run metric gathering.
    """
    data = pd.read_csv(file)

    start = data["start_micros"].min()
    end = data["end_micros"].max()
    count = data["start_micros"].count()
    total = (end - start) / 10**6
    thput = count / total

    latencies = (data["end_micros"] - data["start_micros"]) / 1000
    latency_p50 = latencies.quantile(0.5)
    latency_p90 = latencies.quantile(0.9)
    latency_p99 = latencies.quantile(0.99)
    latency_p999 = latencies.quantile(0.999)

    logging.info("             count: %d", count)
    logging.info("         total (s): %d", total)
    logging.info("throughput (req/s): %d", thput)
    logging.info("  p50 latency (ms): %d", latency_p50)
    logging.info("  p90 latency (ms): %d", latency_p90)
    logging.info("  p99 latency (ms): %d", latency_p99)
    logging.info("p99.9 latency (ms): %d", latency_p999)

    group = name
    with cimetrics.upload.metrics(complete=False) as metrics:
        metrics.put(f"{cmd} throughput (req/s)^", thput, group=group)
        metrics.put(f"{cmd} latency p50 (ms)", latency_p50, group=group)
        metrics.put(f"{cmd} latency p90 (ms)", latency_p90, group=group)
        metrics.put(f"{cmd} latency p99 (ms)", latency_p99, group=group)
        metrics.put(f"{cmd} latency p99.9 (ms)", latency_p999, group=group)


# only run multiple things for prefill_num_keys when it is actually a range bench
def get_prefill_num_keys(bench_cmd: List[str], num_keys: List[int]) -> List[int]:
    """
    Get the number of keys to prefill the datastore with.
    """
    if bench_cmd[0] == "range":
        return num_keys
    return [0]


def get_arguments():
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--sgx", action="store_true")
    parser.add_argument("--no-sgx", action="store_true")
    parser.add_argument("--no-tls", action="store_true")
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
        help="number of keys to fill datastore with before "
        "executing range benchmarks (between 0 and 1000)",
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

    return args


def main():
    """
    Run everything.
    """
    args = get_arguments()

    bench_dir = "bench"
    port = 8000

    # make the bench directory
    shutil.rmtree(bench_dir, ignore_errors=True)
    os.makedirs(bench_dir)

    # pylint: disable=too-many-nested-blocks
    for bench_cmd in args.bench_cmds:
        logging.info("benching with extra args %s", bench_cmd)

        bench_cmd_string = "_".join(bench_cmd)
        bench_dir = os.path.join(bench_dir, bench_cmd_string)
        os.makedirs(bench_dir)

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
                                store = EtcdStore(bench_dir, etcd_config)
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
                            store = EtcdStore(bench_dir, etcd_config)
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
                                if args.no_sgx:
                                    # virtual
                                    store = LSKVStore(bench_dir, lskv_config)
                                    timings_file = run_benchmark(store, bench_cmd)
                                    run_metrics(
                                        store.config.to_str(),
                                        bench_cmd[0],
                                        timings_file,
                                    )

                                # sgx
                                if args.sgx:
                                    lskv_config.sgx = True
                                    store = LSKVStore(bench_dir, lskv_config)
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
