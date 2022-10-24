#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Perf system benchmark.

This benchmark is primarily for comparing http1 and http2 performance of LSKV over the JSON API.
"""

import argparse
import base64
import csv
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Dict, List

import httpx
from loguru import logger

import common
from common import Store
from stores import LSKVStore

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

logger.remove(0)
logger.add(sys.stdout, level="INFO")

BENCH_DIR = os.path.join(common.BENCH_DIR, "perf")


def b64encode(in_str: str) -> str:
    """
    Base64 encode a string.
    """
    return base64.b64encode(in_str.encode("utf-8")).decode("utf-8")


@dataclass
class PerfConfig(common.Config):
    """
    Benchmark configuration.
    """

    def bench_name(self) -> str:
        return "perf"


class PerfBenchmark(common.Benchmark):
    """
    Benchmark implementation for serial requests.
    """

    def __init__(self, config: PerfConfig):
        self.config = config

    def submit_requests(self, store: Store):
        """
        Submit the requests to the datastore.
        """
        timings_file = os.path.join(self.config.output_dir(), "timings.csv")
        with open(timings_file, "w", encoding="utf-8") as timings:
            csv_writer = csv.writer(timings)
            csv_writer.writerow(["start_us", "latency_us", "path", "status"])

            address = f"{self.config.scheme()}://127.0.0.1:{self.config.port}"

            def send_request(
                client: httpx.Client,
                responses,
                path: str,
                body: Dict[str, str],
                i: int,
            ):
                logger.debug(
                    "sending post request {} to {} data={}",
                    i,
                    address + path,
                    body,
                )
                start_ns = time.time_ns()
                resp = client.post(address + path, json=body)
                if resp.status_code != 200:
                    logger.warning("request failed: {}", resp.text)
                end_ns = time.time_ns()
                status = resp.status_code
                start_us = start_ns / 1000
                latency_us = (end_ns - start_ns) / 1000
                responses.writerow([start_us, latency_us, path, status])

            cacert = store.cacert()
            client_cert = (store.cert(), store.key())
            with httpx.Client(
                http2=self.config.http == 2, verify=cacert, cert=client_cert
            ) as client:
                for i in range(100):
                    send_request(
                        client,
                        csv_writer,
                        "/v3/kv/range",
                        {"key": b64encode(f"key{i}")},
                        i,
                    )
                for i in range(100):
                    send_request(
                        client,
                        csv_writer,
                        "/v3/kv/put",
                        {
                            "key": b64encode(f"key{i}"),
                            "value": b64encode(f"value{i}"),
                        },
                        i,
                    )
                for i in range(100):
                    send_request(
                        client,
                        csv_writer,
                        "/v3/kv/range",
                        {"key": b64encode(f"key{i}")},
                        i,
                    )
                for i in range(100):
                    send_request(
                        client,
                        csv_writer,
                        "/v3/kv/delete_range",
                        {"key": b64encode(f"key{i}")},
                        i,
                    )


def run_benchmark(config: PerfConfig, store: Store, benchmark: PerfBenchmark) -> str:
    """
    Run the benchmark for the given store with the given bench command.
    """
    with store:
        store.wait_for_ready()

        logger.info("submit requests")
        benchmark.submit_requests(store)
        logger.info("submitted requests")

        timings_file = os.path.join(config.output_dir(), "timings.csv")

    # pylint: disable=duplicate-code
    return timings_file


# pylint: disable=duplicate-code
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

    args = parser.parse_args()

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

    for common_config in common.make_common_configurations(args):
        conf = PerfConfig(
            **asdict(common_config),
        )
        configs.append(conf)

    return configs


if __name__ == "__main__":
    common.main("perf", get_arguments, make_configurations, execute_config)
