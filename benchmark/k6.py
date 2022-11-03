#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run benchmarks in various configurations for each defined datastore.
"""

import argparse
import os
from dataclasses import dataclass, asdict
from typing import List

import common
from common import Store
from stores import LSKVStore
from loguru import logger

BENCH_DIR = os.path.join(common.BENCH_DIR, "k6")


# pylint: disable=too-many-instance-attributes
@dataclass
class K6Config(common.Config):
    """
    Config holds the configuration options for a given benchmark run.
    """

    rate: int
    vus: int

    def bench_name(self) -> str:
        """
        Get the name of the benchmark.
        """
        return "k6"


class K6Benchmark(common.Benchmark):
    """
    YCS benchmark.
    """

    def __init__(self, config: K6Config):
        self.config = config

    def run_cmd(self, _store: Store) -> List[str]:
        """
        Return the command to run the benchmark for the given store.
        """
        timings_file = os.path.join(self.config.output_dir(), "timings.csv")
        bench = [
            "bin/k6",
            "run",
            "--out",
            f"csv={timings_file}",
            "--rps",
            str(self.config.rate),
            "--vus",
            str(self.config.vus),
            "benchmark/k6.js",
        ]
        logger.debug("run cmd: %s", bench)
        return bench


# pylint: disable=duplicate-code
def run_benchmark(config: K6Config, store: Store, benchmark: K6Benchmark) -> str:
    """
    Run the benchmark for the given store with the given bench command.
    """
    with store:
        store.wait_for_ready()

        logger.info("starting benchmark")
        run_cmd = benchmark.run_cmd(store)
        common.run(run_cmd, "bench", config.output_dir())
        logger.info("stopping benchmark")

        timings_file = os.path.join(config.output_dir(), "timings.csv")

    return timings_file


# pylint: disable=duplicate-code
# pylint: disable=too-many-locals
def run_metrics(_name: str, _cmd: str, file: str):
    """
    Run metric gathering.
    """
    if not os.path.exists(file):
        logger.warning("no metrics file found at %s", file)
        return
    logger.warning("no metrics implemented yet")


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
        help="Maximum requests per second",
    )
    parser.add_argument(
        "--vus",
        action="extend",
        nargs="+",
        type=int,
        default=[],
        help="Number of virtual users to use",
    )

    args = parser.parse_args()

    if not args.rate:
        args.rate = [1000]
    if not args.vus:
        args.vus = [20]

    return args


# pylint: disable=duplicate-code
def execute_config(config: K6Config):
    """
    Execute the given configuration.
    """
    if config.store == "etcd":
        logger.warning("skipping etcd for k6 benchmark")
        return
    store = LSKVStore(config)
    benchmark = K6Benchmark(config)

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


def make_configurations(args: argparse.Namespace) -> List[K6Config]:
    """
    Build up a list of configurations to run.
    """
    configs = []

    for common_config in common.make_common_configurations(args):
        for rate in args.rate:
            logger.debug("adding rate: {}", rate)
            for vus in args.vus:
                logger.debug("adding vus: {}", vus)
                conf = K6Config(
                    **asdict(common_config),
                    rate=rate,
                    vus=vus,
                )
                configs.append(conf)

    return configs


if __name__ == "__main__":
    common.main("k6", get_arguments, make_configurations, execute_config)
