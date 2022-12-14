#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Common module for benchmark utils.
"""

import abc
import argparse
import copy
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from hashlib import sha256
from subprocess import Popen
from typing import Callable, List, TypeVar

# pylint: disable=import-error
import cimetrics.upload  # type: ignore
import typing_extensions
from loguru import logger

# want runs to take a limited number of seconds if they can handle the rate
DESIRED_DURATION_S = 20

BENCH_DIR = "bench"


# pylint: disable=too-many-instance-attributes
@dataclass
class Config:
    """
    Store of config to setup and run a benchmark instance.
    """

    # pylint: disable=duplicate-code
    store: str
    port: int
    tls: bool
    enclave: str
    nodes: int
    worker_threads: int
    sig_tx_interval: int
    sig_ms_interval: int
    ledger_chunk_bytes: str
    snapshot_tx_interval: int
    http_version: int

    def bench_name(self) -> str:
        """
        Get the name of the benchmark.
        """
        return "base"

    def output_dir(self) -> str:
        """
        Return the output directory for this datastore.
        """
        config_str = json.dumps(asdict(self))
        hashed_config = sha256(config_str.encode("utf-8")).hexdigest()
        out_dir = os.path.join(BENCH_DIR, self.bench_name(), hashed_config)
        return out_dir

    def scheme(self) -> str:
        """
        Return the scheme used to connect to this store.
        """
        if self.tls:
            return "https"
        return "http"

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


class Store(abc.ABC):
    """
    The base store for running benchmarks against.
    """

    # pylint: disable=duplicate-code
    def __init__(self, config: Config):
        self.config = config
        self.proc = None

    def __enter__(self):
        self.proc = self.spawn()

    def __exit__(
        self, ex_type, ex_value, ex_traceback
    ) -> typing_extensions.Literal[False]:
        if self.proc:
            logger.info("terminating store process")
            self.proc.terminate()
            # give it some time to shutdown
            tries = 30
            i = 0
            while self.proc.poll() is None and i < tries:
                time.sleep(1)
                i += 1
            if self.proc.poll() is None:
                # process is still running, kill it
                logger.info("killing store process")
                self.proc.kill()
            self.proc.wait()
            logger.info("stopped {}", self.config.to_str())
            logger.info("killing cchost")
            subprocess.run(["pkill", "cchost"], check=True)

        self.cleanup()
        return False

    @abc.abstractmethod
    def spawn(self) -> Popen:
        """
        Spawn the datastore process.
        """
        raise NotImplementedError

    def wait_for_ready(self):
        """
        Wait for the datastore to be ready to accept requests.
        """
        self._wait_for_ready(self.config.port)

    def _wait_for_ready(self, port: int, tries=120) -> bool:
        client = self.client()
        client += ["get", "missing key", "-w", "json"]
        if self.config.http_version == 1:
            client = [
                "curl",
                "--cacert",
                self.cacert(),
                "--cert",
                self.cert(),
                "--key",
                self.key(),
                "-X",
                "POST",
                f"{self.config.scheme()}://127.0.0.1:{self.config.port}/v3/kv/range",
                "-d",
                '{"key":"bWlzc2luZyBrZXkK"}',
                "-H",
                "Content-Type: application/json",
            ]

        for i in range(0, tries):
            logger.debug("running ready check with cmd {}", client)
            # pylint: disable=consider-using-with
            try:
                proc = subprocess.run(client, capture_output=True, check=True)
                if proc.returncode == 0:
                    result = proc.stdout.decode("utf-8")
                    logger.info(
                        "successfully ran wait check and got response {}", result
                    )
                    result_j = json.loads(result)
                    if "header" in result_j:
                        logger.info(
                            "finished waiting for port ({}) to be open, try {}", port, i
                        )
                        return True
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                pass
            logger.debug("waiting for port ({}) to be open, try {}", port, i)
            time.sleep(1)
        logger.error("took too long waiting for port {} ({}s)", port, tries)
        return False

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


# pylint: disable=too-few-public-methods
class Benchmark(abc.ABC):
    """
    Type of benchmark to run.
    """

    def setup_cmd(self, _store: Store) -> List[str]:
        """
        Return the command to setup the benchmark.
        """
        # not everything needs setup
        return []


def get_argument_parser() -> argparse.ArgumentParser:
    """
    Get the default argument parser with common flags.
    """
    parser = argparse.ArgumentParser(description="Benchmark")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument(
        "--enclave",
        type=str,
        choices=["virtual", "sgx"],
        action="extend",
        nargs="+",
        help="enclave to use",
    )
    parser.add_argument("--etcd", action="store_true")
    parser.add_argument("--http1", action="store_true")
    parser.add_argument("--http2", action="store_true")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--nodes", action="extend", nargs="+", type=int)
    parser.add_argument("--worker-threads", action="extend", nargs="+", type=int)
    parser.add_argument("--sig-tx-intervals", action="extend", nargs="+", type=int)
    parser.add_argument("--sig-ms-intervals", action="extend", nargs="+", type=int)
    parser.add_argument("--ledger-chunk-bytes", action="extend", nargs="+", type=str)
    parser.add_argument("--snapshot-tx-intervals", action="extend", nargs="+", type=int)
    return parser


def set_default_args(args: argparse.Namespace):
    """
    Set the default arguments for common args.
    """
    # set default if not set
    if not args.nodes:
        args.nodes = [1]
    if not args.worker_threads:
        args.worker_threads = [0]
    if not args.sig_tx_intervals:
        args.sig_tx_intervals = [5000]
    if not args.sig_ms_intervals:
        args.sig_ms_intervals = [1000]
    if not args.ledger_chunk_bytes:
        args.ledger_chunk_bytes = ["5MB"]
    if not args.snapshot_tx_intervals:
        args.snapshot_tx_intervals = [10000]


def wait_with_timeout(
    process: Popen, duration_seconds=10 * DESIRED_DURATION_S, name=""
):
    """
    Wait for a process to complete, but timeout after the given duration.
    """
    for i in range(0, duration_seconds):
        res = process.poll()
        if res is None:
            # process still running
            logger.debug("waiting for {} process to complete, try {}", name, i)
            time.sleep(1)
        else:
            # process finished
            if res == 0:
                logger.info(
                    "{} process completed successfully within timeout (took {}s)",
                    name,
                    i,
                )
            else:
                logger.error(
                    "{} process failed within timeout (took {}s): code {}", name, i, res
                )
            return

    # didn't finish in time
    logger.error("killing {} process after timeout of {}s", name, duration_seconds)
    process.kill()
    process.wait()
    return


# pylint: disable=too-many-branches
def make_common_configurations(args: argparse.Namespace) -> List[Config]:
    """
    Make the common configurations to run benchmarks against.
    """
    port = 8000
    configs = []
    # pylint: disable=too-many-nested-blocks
    for nodes in args.nodes:
        logger.debug("adding nodes: {}", nodes)
        if args.etcd:
            if args.insecure:
                logger.debug("adding insecure etcd")
                etcd_config = Config(
                    store="etcd",
                    port=port,
                    tls=False,
                    enclave="virtual",
                    nodes=nodes,
                    http_version=2,
                    worker_threads=0,
                    sig_tx_interval=0,
                    sig_ms_interval=0,
                    ledger_chunk_bytes="",
                    snapshot_tx_interval=0,
                )
                configs.append(etcd_config)

            logger.debug("adding tls etcd")
            etcd_config = Config(
                store="etcd",
                port=port,
                tls=True,
                enclave="virtual",
                nodes=nodes,
                http_version=2,
                worker_threads=0,
                sig_tx_interval=0,
                sig_ms_interval=0,
                ledger_chunk_bytes="",
                snapshot_tx_interval=0,
            )
            configs.append(etcd_config)

        # pylint: disable=too-many-nested-blocks
        for worker_threads in args.worker_threads:
            logger.debug("adding worker threads: {}", worker_threads)
            for sig_tx_interval in args.sig_tx_intervals:
                logger.debug("adding sig_tx_interval: {}", sig_tx_interval)
                for sig_ms_interval in args.sig_ms_intervals:
                    logger.debug("adding sig_ms_interval: {}", sig_ms_interval)
                    for ledger_chunk_bytes in args.ledger_chunk_bytes:
                        logger.debug(
                            "adding ledger_chunk_bytes: {}", ledger_chunk_bytes
                        )
                        for snapshot_tx_interval in args.snapshot_tx_intervals:
                            logger.debug(
                                "adding snapshot_tx_interval: {}", snapshot_tx_interval
                            )
                            lskv_config = Config(
                                store="lskv",
                                port=port,
                                tls=True,
                                enclave="virtual",
                                nodes=nodes,
                                http_version=1,
                                worker_threads=worker_threads,
                                sig_tx_interval=sig_tx_interval,
                                sig_ms_interval=sig_ms_interval,
                                ledger_chunk_bytes=ledger_chunk_bytes,
                                snapshot_tx_interval=snapshot_tx_interval,
                            )
                            if "virtual" in args.enclave:
                                lskv_config = copy.deepcopy(lskv_config)
                                logger.debug("adding virtual lskv")
                                if args.http1:
                                    lskv_config = copy.deepcopy(lskv_config)
                                    lskv_config.http_version = 1
                                    logger.debug("adding http1 lskv")
                                    configs.append(lskv_config)
                                if args.http2:
                                    lskv_config = copy.deepcopy(lskv_config)
                                    lskv_config.http_version = 2
                                    logger.debug("adding http2 lskv")
                                    configs.append(lskv_config)

                            # sgx
                            if "sgx" in args.enclave:
                                logger.debug("adding sgx lskv")
                                lskv_config = copy.deepcopy(lskv_config)
                                lskv_config.enclave = "sgx"
                                if args.http1:
                                    lskv_config = copy.deepcopy(lskv_config)
                                    lskv_config.http_version = 1
                                    logger.debug("adding http1 lskv")
                                    configs.append(lskv_config)
                                if args.http2:
                                    lskv_config = copy.deepcopy(lskv_config)
                                    lskv_config.http_version = 2
                                    logger.debug("adding http2 lskv")
                                    configs.append(lskv_config)

    return configs


def run(cmd: List[str], name: str, output_dir: str):
    """
    Make a popen object from a command.
    """
    logger.debug("running cmd: {}", cmd)
    with open(os.path.join(output_dir, f"{name}.out"), "w", encoding="utf-8") as out:
        with open(
            os.path.join(output_dir, f"{name}.err"),
            "w",
            encoding="utf-8",
        ) as err:
            # pylint: disable=consider-using-with
            proc = Popen(cmd, stdout=out, stderr=err)
            wait_with_timeout(proc, name=name)


C = TypeVar("C", bound=Config)


def main(
    benchmark: str,
    get_arguments: Callable[[], argparse.Namespace],
    make_configurations: Callable[[argparse.Namespace], List[C]],
    execute_config: Callable[[C], None],
):
    """
    Run everything.
    """
    args = get_arguments()
    set_default_args(args)

    logger.info("got arguments: {}", args)
    logger.remove()
    if args.verbose:
        logger.add(sys.stdout, level="DEBUG")
    else:
        logger.add(sys.stdout, level="INFO")

    bench_dir = os.path.join(BENCH_DIR, benchmark)

    # make the bench directory
    os.makedirs(bench_dir, exist_ok=True)

    configs = make_configurations(args)

    logger.debug("made {} configurations", len(configs))

    for i, config in enumerate(configs):
        if os.path.exists(config.output_dir()):
            logger.warning(
                "skipping config (output dir already exists) {}/{}: {}",
                i + 1,
                len(configs),
                config,
            )
            continue
        # setup results dir
        os.makedirs(config.output_dir(), exist_ok=True)
        # write the config out
        config_path = os.path.join(config.output_dir(), "config.json")
        with open(config_path, "w", encoding="utf-8") as config_f:
            config_dict = asdict(config)
            logger.info("writing config to file {}", config_path)
            config_f.write(json.dumps(config_dict, indent=2))

        logger.info("executing config {}/{}: {}", i + 1, len(configs), config)
        execute_config(config)

    with cimetrics.upload.metrics():
        pass
