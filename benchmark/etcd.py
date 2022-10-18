#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run benchmarks in various configurations for each defined datastore.
"""

import argparse
import copy
import logging
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from subprocess import Popen
from typing import List

import cimetrics.upload  # type: ignore
import pandas as pd  # type: ignore

import common
from common import Benchmark, Config, Store, wait_with_timeout, DESIRED_DURATION_S
from stores import EtcdStore, LSKVStore

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)


# pylint: disable=too-many-instance-attributes
@dataclass
class EtcdConfig(Config):
    """
    Config holds the configuration options for a given benchmark run.
    """

    bench_args: List[str]
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
            if isinstance(value, list):
                string_parts.append(f"{k}={'_'.join(value)}")
            else:
                string_parts.append(f"{k}={value}")
        return ",".join(string_parts)

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


class EtcdBenchmark(Benchmark):
    """
    Etcd benchmark.
    """

    def run_cmd(self, store: Store) -> List[str]:
        """
        Return the command to run the benchmark for the given store.
        """
        timings_file = os.path.join(store.config.output_dir(), "timings.csv")
        bench = [
            "bin/benchmark",
            "--endpoints",
            f"{store.config.scheme()}://127.0.0.1:{store.config.port}",
            "--clients",
            str(store.config.clients),
            "--conns",
            str(store.config.connections),
            "--csv-file",
            timings_file,
        ]
        bench += ["--rate", str(store.config.rate), "--total", str(store.config.total)]
        if store.config.tls:
            bench += [
                "--cacert",
                store.cacert(),
                "--cert",
                store.cert(),
                "--key",
                store.key(),
            ]
        bench += store.config.bench_args
        return bench

    def name(self) -> str:
        """
        Get the name of the benchmark.
        """
        return "etcd"


def prefill_datastore(store: Store, start: int, end: int):
    """
    Fill the datastore with a range of keys.
    """
    time.sleep(1)
    client = store.client()
    i = 0
    num_keys = store.config.prefill_num_keys
    value_size = store.config.prefill_value_size
    logging.debug("prefilling %s keys", num_keys)
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
    logging.debug("prefilled %s keys", i)


def run_benchmark(store: Store, benchmark: Benchmark) -> str:
    """
    Run the benchmark for the given store with the given bench command.
    """
    with store:
        store.wait_for_ready()

        if store.config.bench_args[0] == "range":
            # need to prefill the store with data for it to get
            start = int(store.config.bench_args[1])
            end = int(store.config.bench_args[2])
            logging.info(
                "prefilling datastore with %s keys in range [%s, %s)",
                store.config.prefill_num_keys,
                start,
                end,
            )
            prefill_datastore(store, start, end)

        logging.info("starting benchmark")
        timings_file = os.path.join(store.config.output_dir(), "timings.csv")

        run_cmd = benchmark.run_cmd(store)
        with open(
            os.path.join(store.config.output_dir(), "bench.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(store.config.output_dir(), "bench.err"),
                "w",
                encoding="utf-8",
            ) as err:
                # pylint: disable=consider-using-with
                proc = Popen(run_cmd, stdout=out, stderr=err)
                wait_with_timeout(proc, name="benchmark")

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

    logging.info("             count: %s", count)
    logging.info("         total (s): %s", total)
    logging.info("throughput (req/s): %s", thput)
    logging.info("  p50 latency (ms): %s", latency_p50)
    logging.info("  p90 latency (ms): %s", latency_p90)
    logging.info("  p99 latency (ms): %s", latency_p99)
    logging.info("p99.9 latency (ms): %s", latency_p999)

    group = name
    with cimetrics.upload.metrics(complete=False) as metrics:
        metrics.put(f"{cmd} throughput (req/s)^", thput, group=group)
        metrics.put(f"{cmd} latency p50 (ms)", latency_p50, group=group)
        metrics.put(f"{cmd} latency p90 (ms)", latency_p90, group=group)
        metrics.put(f"{cmd} latency p99 (ms)", latency_p99, group=group)
        metrics.put(f"{cmd} latency p99.9 (ms)", latency_p999, group=group)


# only run multiple things for prefill_num_keys when it is actually a range bench
def get_prefill_num_keys(bench_args: List[str], num_keys: List[int]) -> List[int]:
    """
    Get the number of keys to prefill the datastore with.
    """
    if bench_args[0] == "range":
        return num_keys
    return [0]


def get_arguments():
    """
    Parse command line arguments.
    """
    parser = common.get_argument_parser()
    parser.add_argument("--sgx", action="store_true")
    parser.add_argument("--no-sgx", action="store_true")
    parser.add_argument("--no-tls", action="store_true")
    parser.add_argument("--worker-threads", action="extend", nargs="+", type=int)
    parser.add_argument("--clients", action="extend", nargs="+", type=int)
    parser.add_argument("--connections", action="extend", nargs="+", type=int)
    parser.add_argument(
        "--bench-args", action="extend", nargs="+", type=str, default=[]
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

    args.bench_args = [s.split() for s in args.bench_args]
    if not args.bench_args:
        args.bench_args = [
            ["put"],
            ["range", "0000", "1000"],
            ["txn-put"],
            ["txn-mixed", "txn-mixed-key"],
        ]

    return args


def run_bench_configuration(
    benchmark: Benchmark, args: argparse.Namespace, bench_args: List[str]
):
    """
    Run a benchmark configuration.
    """
    port = 8000
    for clients in args.clients:
        for conns in args.connections:
            # for prefill_num_keys in get_prefill_num_keys(
            #     bench_args, args.prefill_num_keys
            # ):
            #     for prefill_value_size in get_prefill_num_keys(
            #         bench_args, args.prefill_value_size
            #     ):
            for rate in args.rate:
                if args.no_tls:
                    etcd_config = EtcdConfig(
                        bench_args,
                        "etcd",
                        port,
                        tls=False,
                        sgx=False,
                        worker_threads=0,
                        clients=clients,
                        connections=conns,
                        prefill_num_keys=0,
                        prefill_value_size=0,
                        rate=rate,
                    )
                    store = EtcdStore(etcd_config)
                    timings_file = run_benchmark(store, benchmark)
                    run_metrics(store.config.to_str(), bench_args[0], timings_file)

                etcd_config = EtcdConfig(
                    bench_args,
                    "etcd",
                    port,
                    tls=True,
                    sgx=False,
                    worker_threads=0,
                    clients=clients,
                    connections=conns,
                    prefill_num_keys=0,
                    prefill_value_size=0,
                    rate=rate,
                )
                store = EtcdStore(etcd_config)
                timings_file = run_benchmark(store, benchmark)
                run_metrics(store.config.to_str(), bench_args[0], timings_file)

                for worker_threads in args.worker_threads:
                    lskv_config = EtcdConfig(
                        bench_args,
                        "lskv",
                        port,
                        tls=True,
                        sgx=False,
                        worker_threads=worker_threads,
                        clients=clients,
                        connections=conns,
                        prefill_num_keys=0,
                        prefill_value_size=0,
                        rate=rate,
                    )
                    if args.no_sgx:
                        # virtual
                        store = LSKVStore(lskv_config)
                        timings_file = run_benchmark(
                            store,
                            benchmark,
                        )
                        run_metrics(
                            store.config.to_str(),
                            bench_args[0],
                            timings_file,
                        )

                    # sgx
                    if args.sgx:
                        lskv_config.sgx = True
                        store = LSKVStore(lskv_config)
                        timings_file = run_benchmark(
                            store,
                            benchmark,
                        )
                        run_metrics(
                            store.config.to_str(),
                            bench_args[0],
                            timings_file,
                        )


def execute_config(config: EtcdConfig):
    """
    Execute the given configuration.
    """
    store = EtcdStore(config) if config.name == "etcd" else LSKVStore(config)
    benchmark = EtcdBenchmark()

    timings_file = run_benchmark(
        store,
        benchmark,
    )
    run_metrics(
        config.to_str(),
        config.bench_args[0],
        timings_file,
    )


def make_configurations(args: argparse.Namespace) -> List[Config]:
    """
    Build up a list of configurations to run.
    """
    configs = []
    port = 8000

    # pylint: disable=too-many-nested-blocks
    for bench_args in args.bench_args:
        logging.debug("adding bench-args: %s", bench_args)
        for clients in args.clients:
            logging.debug("adding clients: %s", clients)
            for conns in args.connections:
                logging.debug("adding connections: %s", conns)
                for prefill_num_keys in get_prefill_num_keys(
                    bench_args, args.prefill_num_keys
                ):
                    logging.debug("adding prefill_num_keys: %s", prefill_num_keys)
                    for prefill_value_size in get_prefill_num_keys(
                        bench_args, args.prefill_value_size
                    ):
                        logging.debug(
                            "adding prefill_value_size: %s", prefill_value_size
                        )
                        for rate in args.rate:
                            logging.debug("adding rate: %s", rate)
                            if args.no_tls:
                                logging.debug("adding no_tls etcd")
                                etcd_config = EtcdConfig(
                                    bench_args,
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
                                configs.append(etcd_config)

                            logging.debug("adding tls etcd")
                            etcd_config = EtcdConfig(
                                bench_args,
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
                            configs.append(etcd_config)

                            for worker_threads in args.worker_threads:
                                logging.debug(
                                    "adding worker threads: %s", worker_threads
                                )
                                lskv_config = EtcdConfig(
                                    bench_args,
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
                                    logging.debug("adding no_sgx lskv")
                                    configs.append(lskv_config)

                                # sgx
                                if args.sgx:
                                    logging.debug("adding sgx lskv")
                                    lskv_config = copy.deepcopy(lskv_config)
                                    lskv_config.sgx = True
                                    configs.append(lskv_config)

    return configs


def main():
    """
    Run everything.
    """
    args = get_arguments()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    bench_dir = "bench"

    # make the bench directory
    shutil.rmtree(bench_dir, ignore_errors=True)
    os.makedirs(bench_dir)

    configs = make_configurations(args)

    logging.debug("made %d configurations", len(configs))

    for i, config in enumerate(configs):
        logging.info("executing config %d/%d: %s", i + 1, len(configs), config)
        execute_config(config)

    with cimetrics.upload.metrics():
        pass


if __name__ == "__main__":
    main()
