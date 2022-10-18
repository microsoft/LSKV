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
from dataclasses import dataclass
from subprocess import Popen
from typing import List

import cimetrics.upload  # type: ignore
import pandas as pd  # type: ignore

import common
from common import Store, wait_with_timeout, DESIRED_DURATION_S
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
            f"measurement.raw.output_file={timings_file}",
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
            "--prop",
            f"etcd.endpoints={self.config.scheme()}://127.0.0.1:{self.config.port}",
            "--prop",
            "measurementtype=raw",
            "--prop",
            f"measurement.raw.output_file={timings_file}",
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
        with open(
            os.path.join(config.output_dir(), "load.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(config.output_dir(), "load.err"),
                "w",
                encoding="utf-8",
            ) as err:
                # pylint: disable=consider-using-with
                proc = Popen(load_cmd, stdout=out, stderr=err)
                wait_with_timeout(proc, name="load")
        logging.info("finished load phase")

        logging.info("starting benchmark")
        timings_file = os.path.join(config.output_dir(), "timings.csv")

        run_cmd = benchmark.run_cmd(store)
        with open(
            os.path.join(config.output_dir(), "bench.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(config.output_dir(), "bench.err"),
                "w",
                encoding="utf-8",
            ) as err:
                # pylint: disable=consider-using-with
                proc = Popen(run_cmd, stdout=out, stderr=err)
                wait_with_timeout(proc, name="benchmark")

        logging.info("stopping benchmark for %s", config.to_str())

    return timings_file


# pylint: disable=too-many-locals
def run_metrics(name: str, cmd: str, file: str):
    """
    Run metric gathering.
    """
    if not os.path.exists(file):
        logging.warning("no metrics file found at %s", file)
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


def get_arguments():
    """
    Parse command line arguments.
    """
    parser = common.get_argument_parser()
    parser.add_argument("--sgx", action="store_true")
    parser.add_argument("--virtual", action="store_true")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--worker-threads", action="extend", nargs="+", type=int)

    args = parser.parse_args()

    # set default if not set
    if not args.worker_threads:
        args.worker_threads = [0]

    return args


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
    port = 8000

    for workload in ["a", "b", "c", "d", "e", "f"]:
        workload = f"workload{workload}"
        logging.debug("adding workload: %s", workload)
        if args.insecure:
            logging.debug("adding insecure etcd")
            etcd_config = YCSBConfig(
                store="etcd",
                port=port,
                tls=False,
                sgx=False,
                worker_threads=0,
                workload=workload,
            )
            configs.append(etcd_config)

        logging.debug("adding tls etcd")
        etcd_config = YCSBConfig(
            store="etcd",
            port=port,
            tls=True,
            sgx=False,
            worker_threads=0,
            workload=workload,
        )
        configs.append(etcd_config)

        for worker_threads in args.worker_threads:
            logging.debug("adding worker threads: %s", worker_threads)
            lskv_config = YCSBConfig(
                store="lskv",
                port=port,
                tls=True,
                sgx=False,
                worker_threads=worker_threads,
                workload=workload,
            )
            if args.virtual:
                # virtual
                logging.debug("adding virtual lskv")
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

    # make the bench directory
    shutil.rmtree(BENCH_DIR, ignore_errors=True)
    os.makedirs(BENCH_DIR)

    configs = make_configurations(args)

    logging.debug("made %d configurations", len(configs))

    for i, config in enumerate(configs):
        logging.info("executing config %d/%d: %s", i + 1, len(configs), config)
        execute_config(config)

    with cimetrics.upload.metrics():
        pass


if __name__ == "__main__":
    main()
