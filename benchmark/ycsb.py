#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run benchmarks in various configurations for each defined datastore.
"""

import argparse
import logging
import os
from dataclasses import dataclass, asdict
from typing import List

import common
from common import Store
from stores import EtcdStore, LSKVStore

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

BENCH_DIR = os.path.join(common.BENCH_DIR, "ycsb")


# pylint: disable=too-many-instance-attributes
@dataclass
class YCSBConfig(common.Config):
    """
    Config holds the configuration options for a given benchmark run.
    """

    workload: str
    rate: int

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

    def load_cmd(self, store: Store) -> List[str]:
        """
        Return the command to run the benchmark for the given store.
        """
        timings_file = os.path.join(self.config.output_dir(), "timings.csv")
        bench = [
            "bin/go-ycsb",
            "load",
            "etcd",
            "--prop",
            f"etcd.endpoints={self.config.scheme()}://127.0.0.1:{self.config.port}",
            "--prop",
            "measurementtype=raw",
            "--prop",
            f"measurement.output_file={timings_file}",
            "--property_file",
            self.path_to_workload(),
        ]
        logging.debug("load cmd: %s", bench)
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

    def run_cmd(self, store: Store) -> List[str]:
        """
        Return the command to run the benchmark for the given store.
        """
        timings_file = os.path.join(self.config.output_dir(), "timings.csv")
        bench = [
            "bin/go-ycsb",
            "run",
            "etcd",
            "--target",
            str(self.config.rate),
            "--prop",
            f"etcd.endpoints={self.config.scheme()}://127.0.0.1:{self.config.port}",
            "--prop",
            "measurementtype=raw",
            "--prop",
            f"measurement.output_file={timings_file}",
            "--property_file",
            self.path_to_workload(),
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

        logging.info("starting load phase")
        load_cmd = benchmark.load_cmd(store)
        common.run(load_cmd, "load", config.output_dir())
        logging.info("finished load phase")

        logging.info("starting benchmark")
        run_cmd = benchmark.run_cmd(store)
        common.run(run_cmd, "bench", config.output_dir())
        logging.info("stopping benchmark")

        timings_file = os.path.join(config.output_dir(), "timings.csv")

    return timings_file


# pylint: disable=too-many-locals
def run_metrics(_name: str, _cmd: str, file: str):
    """
    Run metric gathering.
    """
    if not os.path.exists(file):
        logging.warning("no metrics file found at %s", file)
        return
    logging.warning("no metrics implemented yet")


def get_arguments():
    """
    Parse command line arguments.
    """
    parser = common.get_argument_parser()

    parser.add_argument(
        "--rate",
        action="extend",
        nargs="+",
        type=int,
        default=[],
        help="Maximum requests per second (0 is no limit)",
    )

    args = parser.parse_args()

    common.set_default_args(args)

    if not args.rate:
        args.rate = [0]

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

    for workload in ["a", "b", "c", "d", "e", "f"]:
        workload = f"workload{workload}"
        logging.debug("adding workload: %s", workload)
        for rate in args.rate:
            logging.debug("adding rate: %s", rate)
            for common_config in common.make_common_configurations(args):
                conf = YCSBConfig(
                    **asdict(common_config),
                    workload=workload,
                    rate=rate,
                )
                configs.append(conf)

    return configs


if __name__ == "__main__":
    common.main("ycsb", get_arguments, make_configurations, execute_config)
