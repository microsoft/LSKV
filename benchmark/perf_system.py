#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Perf system benchmark.

This benchmark is primarily for comparing http1 and http2 performance of LSKV over the JSON API.
"""

import argparse
import os
from dataclasses import asdict, dataclass
from typing import List

import common
from common import Store
from loguru import logger
from stores import DistributedLSKVStore, LSKVStore

BENCH_DIR = os.path.join(common.BENCH_DIR, "perf")


@dataclass
class PerfConfig(common.Config):
    """
    Benchmark configuration.
    """

    workload: str
    max_inflight_requests: int

    def bench_name(self) -> str:
        return "perf"


class PerfBenchmark(common.Benchmark):
    """
    Benchmark implementation for serial requests.
    """

    def __init__(self, config: PerfConfig):
        self.config = config

    def run_cmd(self, store: Store) -> List[str]:
        """
        Return the command to run the benchmark for the given store.
        """
        ccf_bin = f"/opt/ccf_{self.config.enclave}/bin"
        bench = [
            f"{ccf_bin}/submit",
            "--send-filepath",
            os.path.join(self.config.output_dir(), "requests.parquet"),
            "--response-filepath",
            os.path.join(self.config.output_dir(), "responses.parquet"),
            "--generator-filepath",
            self.config.workload,
            "--max-inflight-requests",
            str(self.config.max_inflight_requests),
            "--cacert",
            store.cacert(),
            "--cert",
            store.cert(),
            "--key",
            store.key(),
        ]
        return bench


def run_benchmark(config: PerfConfig, store: Store, benchmark: PerfBenchmark) -> str:
    """
    Run the benchmark for the given store with the given bench command.
    """
    with store:
        store.wait_for_ready()

        logger.info("starting benchmark")
        run_cmd = benchmark.run_cmd(store)
        common.run(run_cmd, "bench", config.output_dir())
        logger.info("stopping benchmark")

    # pylint: disable=duplicate-code
    return ""


# pylint: disable=duplicate-code
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
        type=str,
        action="extend",
        nargs="+",
        help="The workload files to submit",
    )
    parser.add_argument(
        "--max-inflight-requests",
        type=int,
        action="extend",
        nargs="+",
        help="Number of outstanding requests to allow",
    )

    args = parser.parse_args()

    if not args.max_inflight_requests:
        args.max_inflight_requests = [0]

    return args


# pylint: disable=duplicate-code
def execute_config(config: PerfConfig):
    """
    Execute the given configuration.
    """
    if config.store == "etcd":
        # doesn't work with the etcd API
        logger.info("skipping test with etcd store")
        return
    if config.distributed:
        store = DistributedLSKVStore(config)
    else:
        store = LSKVStore(config)
    benchmark = PerfBenchmark(config)

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


def make_configurations(args: argparse.Namespace) -> List[PerfConfig]:
    """
    Build up a list of configurations to run.
    """
    configs = []

    for workload in args.workloads:
        logger.debug("Adding configuration for workload {}", workload)
        for max_inflight_requests in args.max_inflight_requests:
            logger.debug(
                "Adding configuration for max_inflight_requests {}",
                max_inflight_requests,
            )
            for common_config in common.make_common_configurations(args):
                conf = PerfConfig(
                    **asdict(common_config),
                    workload=workload,
                    max_inflight_requests=max_inflight_requests,
                )
                configs.append(conf)

    return configs


if __name__ == "__main__":
    common.main("perf", get_arguments, make_configurations, execute_config)
