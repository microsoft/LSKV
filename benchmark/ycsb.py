#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run benchmarks in various configurations for each defined datastore.
"""

import argparse
import os
from dataclasses import asdict, dataclass
from typing import List

import common
from common import Store
from loguru import logger
from stores import EtcdStore, LSKVStore

BENCH_DIR = os.path.join(common.BENCH_DIR, "ycsb")


# pylint: disable=too-many-instance-attributes
@dataclass
class YCSBConfig(common.Config):
    """
    Config holds the configuration options for a given benchmark run.
    """

    workload: str
    rate: int
    threads: int

    def bench_name(self) -> str:
        """
        Get the name of the benchmark.
        """
        return "ycsb"


class YCSBenchmark(common.Benchmark):
    """
    YCS benchmark.
    """

    def __init__(self, config: YCSBConfig):
        self.config = config

    def ycsb_cmd(self, store: Store, subcmd: str) -> List[str]:
        """
        Make a core ycsb command.
        """
        bench = [
            "bin/go-ycsb",
            subcmd,
            "etcd",
            "--target",
            str(self.config.rate),
            "--threads",
            str(self.config.threads),
            "--prop",
            "silence=false",
            "--prop",
            f"etcd.endpoints={self.config.scheme()}://127.0.0.1:{self.config.port}",
            "--property_file",
            self.path_to_workload(),
            "--interval",
            "1",
        ]
        if self.config.tls:
            bench += [
                "--prop",
                f"etcd.cacert_file={store.cacert()}",
                "--prop",
                f"etcd.cert_file={store.cert()}",
                "--prop",
                f"etcd.key_file={store.key()}",
            ]
        return bench

    def load_cmd(self, store: Store) -> List[str]:
        """
        Return the command to run the benchmark for the given store.
        """
        bench = self.ycsb_cmd(store, "load")
        logger.debug("load cmd: {}", bench)
        return bench

    def run_cmd(self, store: Store) -> List[str]:
        """
        Return the command to run the benchmark for the given store.
        """
        timings_file = os.path.join(self.config.output_dir(), "timings.csv")
        bench = self.ycsb_cmd(store, "run") + [
            "--prop",
            "measurementtype=raw",
            "--prop",
            f"measurement.output_file={timings_file}",
        ]
        logger.debug("run cmd: {}", bench)
        return bench

    def path_to_workload(self) -> str:
        """
        Return the path to the workload file.
        """
        return os.path.join("3rdparty/go-ycsb/workloads", self.config.workload)


def run_benchmark(config: YCSBConfig, store: Store, benchmark: YCSBenchmark) -> str:
    """
    Run the benchmark for the given store with the given bench command.
    """
    with store:
        store.wait_for_ready()

        logger.info("starting load phase")
        load_cmd = benchmark.load_cmd(store)
        common.run(load_cmd, "load", config.output_dir())
        logger.info("finished load phase")

        logger.info("starting benchmark")
        run_cmd = benchmark.run_cmd(store)
        common.run(run_cmd, "bench", config.output_dir())
        logger.info("stopping benchmark")

        timings_file = os.path.join(config.output_dir(), "timings.csv")

    return timings_file


# pylint: disable=too-many-locals
def run_metrics(_name: str, _cmd: str, file: str):
    """
    Run metric gathering.
    """
    if not os.path.exists(file):
        logger.warning("no metrics file found at {}", file)
        return
    logger.warning("no metrics implemented yet")


def get_arguments():
    """
    Parse command line arguments.
    """
    parser = common.get_argument_parser()

    parser.add_argument(
        "--workloads",
        action="extend",
        nargs="+",
        type=str,
        default=[],
        help="Workload file suffixes to run",
    )

    parser.add_argument(
        "--rate",
        action="extend",
        nargs="+",
        type=int,
        default=[],
        help="Maximum requests per second (0 is no limit)",
    )
    parser.add_argument(
        "--threads",
        action="extend",
        nargs="+",
        type=int,
        default=[],
        help="Threads to use in ycsb",
    )

    args = parser.parse_args()

    if not args.workloads:
        args.workloads = ["a", "b", "c", "d", "e", "f"]
    if not args.rate:
        args.rate = [1000]
    if not args.threads:
        args.threads = [1]

    return args


# pylint: disable=duplicate-code
def execute_config(config: YCSBConfig):
    """
    Execute the given configuration.
    """
    store = EtcdStore(config) if config.store == "etcd" else LSKVStore(config)
    benchmark = YCSBenchmark(config)

    timings_file = run_benchmark(
        config,
        store,
        benchmark,
    )
    run_metrics(
        config.to_str(),
        "todo",
        timings_file,
    )


def make_configurations(args: argparse.Namespace) -> List[YCSBConfig]:
    """
    Build up a list of configurations to run.
    """
    configs = []

    for workload in args.workloads:
        workload = f"workload{workload}"
        logger.debug("adding workload: {}", workload)
        for rate in args.rate:
            logger.debug("adding rate: {}", rate)
            for threads in args.threads:
                logger.debug("adding threads: {}", threads)
                for common_config in common.make_common_configurations(args):
                    conf = YCSBConfig(
                        **asdict(common_config),
                        workload=workload,
                        rate=rate,
                        threads=threads,
                    )
                    configs.append(conf)

    return configs


if __name__ == "__main__":
    common.main("ycsb", get_arguments, make_configurations, execute_config)
