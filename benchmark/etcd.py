#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run benchmarks in various configurations for each defined datastore.
"""

import argparse
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from subprocess import Popen
from typing import List

# pylint: disable=import-error
import cimetrics.upload  # type: ignore
import common
import pandas as pd  # type: ignore
from common import DESIRED_DURATION_S, Store
from loguru import logger
from stores import DistributedLSKVStore, EtcdStore, LSKVStore


# pylint: disable=too-many-instance-attributes
@dataclass
class EtcdConfig(common.Config):
    """
    Config holds the configuration options for a given benchmark run.
    """

    bench_args: List[str]
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

    def bench_name(self) -> str:
        """
        Get the name of the benchmark.
        """
        return "etcd"

    def calculate_total(self) -> int:
        """
        Return the total number of requests to execute.
        """
        # default requests per second (things can time out)
        rate = self.rate
        total = DESIRED_DURATION_S * rate
        return total


class EtcdBenchmark(common.Benchmark):
    """
    Etcd benchmark.
    """

    def __init__(self, config: EtcdConfig):
        self.config = config

    def run_cmd(self, store: Store) -> List[str]:
        """
        Return the command to run the benchmark for the given store.
        """
        timings_file = os.path.join(self.config.output_dir(), "timings.csv")
        bench = [
            "bin/benchmark",
            "--endpoints",
            f"{self.config.scheme()}://127.0.0.1:{self.config.port}",
            "--clients",
            str(self.config.clients),
            "--conns",
            str(self.config.connections),
            "--csv-file",
            timings_file,
        ]
        bench += ["--rate", str(self.config.rate), "--total", str(self.config.total)]
        if self.config.tls:
            bench += [
                "--cacert",
                store.cacert(),
                "--cert",
                store.cert(),
                "--key",
                store.key(),
            ]
        bench += self.config.bench_args
        return bench


def prefill_datastore(config: EtcdConfig, store: Store, start: int, end: int):
    """
    Fill the datastore with a range of keys.
    """
    time.sleep(1)
    client = store.client()
    i = 0
    num_keys = config.prefill_num_keys
    value_size = config.prefill_value_size
    logger.debug("prefilling {} keys", num_keys)
    end_size = len(str(end))
    if num_keys:
        for k in range(start, end, (end - start) // num_keys):
            i += 1
            key = str(k).zfill(end_size)
            value = "v" * value_size
            logger.debug("prefilling {}", key)
            # pylint: disable=consider-using-with
            proc = Popen(
                client + ["put", key, value],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if proc.wait() != 0:
                raise Exception("failed to fill datastore")
    logger.debug("prefilled {} keys", i)


def run_benchmark(config: EtcdConfig, store: Store, benchmark: EtcdBenchmark) -> str:
    """
    Run the benchmark for the given store with the given bench command.
    """
    with store:
        store.wait_for_ready()

        if config.bench_args[0] == "range":
            # need to prefill the store with data for it to get
            start = int(config.bench_args[1])
            end = int(config.bench_args[2])
            logger.info(
                "prefilling datastore with {} keys in range [{}, {})",
                config.prefill_num_keys,
                start,
                end,
            )
            prefill_datastore(config, store, start, end)

        logger.info("starting benchmark")
        timings_file = os.path.join(config.output_dir(), "timings.csv")

        run_cmd = benchmark.run_cmd(store)
        common.run(run_cmd, "bench", config.output_dir())

        logger.info("stopping benchmark for {}", config.to_str())

    return timings_file


# pylint: disable=too-many-locals
def run_metrics(name: str, cmd: str, file: str):
    """
    Run metric gathering.
    """
    if not os.path.exists(file):
        logger.warning("no metrics file found at {}", file)
        return
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

    logger.info("             count: {}", count)
    logger.info("         total (s): {}", total)
    logger.info("throughput (req/s): {}", thput)
    logger.info("  p50 latency (ms): {}", latency_p50)
    logger.info("  p90 latency (ms): {}", latency_p90)
    logger.info("  p99 latency (ms): {}", latency_p99)
    logger.info("p99.9 latency (ms): {}", latency_p999)

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
    # pylint: disable=duplicate-code
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
        args.rate = [1000]

    # pylint: disable=no-member
    args.bench_args = [s.split() for s in args.bench_args]
    if not args.bench_args:
        args.bench_args = [
            ["put"],
            # ["range", "0000", "1000"],
            # ["txn-put"],
            # ["txn-mixed", "txn-mixed-key"],
        ]

    return args


def execute_config(config: EtcdConfig):
    """
    Execute the given configuration.
    """
    if config.store == "etcd":
        store: Store = EtcdStore(config)
    else:
        if config.distributed:
            store = DistributedLSKVStore(config)
        else:
            store = LSKVStore(config)

    benchmark = EtcdBenchmark(config)

    timings_file = run_benchmark(
        config,
        store,
        benchmark,
    )
    run_metrics(
        config.to_str(),
        config.bench_args[0],
        timings_file,
    )


def make_configurations(args: argparse.Namespace) -> List[EtcdConfig]:
    """
    Build up a list of configurations to run.
    """
    configs = []

    # pylint: disable=too-many-nested-blocks
    for bench_args in args.bench_args:
        logger.debug("adding bench-args: {}", bench_args)
        for clients in args.clients:
            logger.debug("adding clients: {}", clients)
            for conns in args.connections:
                logger.debug("adding connections: {}", conns)
                for prefill_num_keys in get_prefill_num_keys(
                    bench_args, args.prefill_num_keys
                ):
                    logger.debug("adding prefill_num_keys: {}", prefill_num_keys)
                    for prefill_value_size in get_prefill_num_keys(
                        bench_args, args.prefill_value_size
                    ):
                        logger.debug(
                            "adding prefill_value_size: {}", prefill_value_size
                        )
                        for rate in args.rate:
                            logger.debug("adding rate: {}", rate)

                            for common_config in common.make_common_configurations(
                                args
                            ):
                                conf = EtcdConfig(
                                    **asdict(common_config),
                                    bench_args=bench_args,
                                    clients=clients,
                                    connections=conns,
                                    prefill_num_keys=prefill_num_keys,
                                    prefill_value_size=prefill_value_size,
                                    rate=rate,
                                )
                                configs.append(conf)

    return configs


if __name__ == "__main__":
    common.main("etcd", get_arguments, make_configurations, execute_config)
