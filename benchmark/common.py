#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Common module for benchmark utils.
"""

import abc
import argparse
import copy
import logging
import os
import time
from dataclasses import asdict, dataclass
from subprocess import Popen
from typing import Callable, List, TypeVar

import cimetrics.upload  # type: ignore
import typing_extensions

# want runs to take a limited number of seconds if they can handle the rate
DESIRED_DURATION_S = 20

BENCH_DIR = "bench"


# pylint: disable=too-many-instance-attributes
@dataclass
class Config:
    """
    Store of config to setup and run a benchmark instance.
    """

    store: str
    port: int
    tls: bool
    sgx: bool
    worker_threads: int
    sig_tx_interval: int
    sig_ms_interval: int
    ledger_chunk_bytes: str
    snapshot_tx_interval: int

    def bench_name(self) -> str:
        """
        Get the name of the benchmark.
        """
        return "base"

    def output_dir(self) -> str:
        """
        Return the output directory for this datastore.
        """
        out_dir = os.path.join(BENCH_DIR, self.bench_name(), self.to_str())
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

    def __init__(self, config: Config):
        self.config = config
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
                    "finished waiting for port (%s) to be open, try %s", port, i
                )
                return True
            logging.debug("waiting for port (%s) to be open, try %s", port, i)
            time.sleep(1)
        logging.error("took too long waiting for port %s (%ss)", port, tries)
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
    parser.add_argument("--sgx", action="store_true")
    parser.add_argument("--virtual", action="store_true")
    parser.add_argument("--insecure", action="store_true")
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
    if not args.worker_threads:
        args.worker_threads = [0]
    if not args.sig_tx_intervals:
        args.sig_tx_intervals = [5000]
    if not args.sig_ms_intervals:
        args.sig_ms_intervals = [100]
    if not args.ledger_chunk_bytes:
        args.ledger_chunk_bytes = ["20KB"]
    if not args.snapshot_tx_intervals:
        args.snapshot_tx_intervals = [10]


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
            logging.debug("waiting for %s process to complete, try %s", name, i)
            time.sleep(1)
        else:
            # process finished
            if res == 0:
                logging.info(
                    "%s process completed successfully within timeout (took %ss)",
                    name,
                    i,
                )
            else:
                logging.error(
                    "%s process failed within timeout (took %ss): code %s", name, i, res
                )
            return

    # didn't finish in time
    logging.error("killing %s process after timeout of %ss", name, duration_seconds)
    process.kill()
    process.wait()
    return


def make_common_configurations(args: argparse.Namespace) -> List[Config]:
    """
    Make the common configurations to run benchmarks against.
    """
    port = 8000
    configs = []
    if args.insecure:
        logging.debug("adding insecure etcd")
        etcd_config = Config(
            store="etcd",
            port=port,
            tls=False,
            sgx=False,
            worker_threads=0,
            sig_tx_interval=0,
            sig_ms_interval=0,
            ledger_chunk_bytes="",
            snapshot_tx_interval=0,
        )
        configs.append(etcd_config)

    logging.debug("adding tls etcd")
    etcd_config = Config(
        store="etcd",
        port=port,
        tls=True,
        sgx=False,
        worker_threads=0,
        sig_tx_interval=0,
        sig_ms_interval=0,
        ledger_chunk_bytes="",
        snapshot_tx_interval=0,
    )
    configs.append(etcd_config)

    # pylint: disable=too-many-nested-blocks
    for worker_threads in args.worker_threads:
        logging.debug("adding worker threads: %s", worker_threads)
        for sig_tx_interval in args.sig_tx_intervals:
            logging.debug("adding sig_tx_interval: %s", sig_tx_interval)
            for sig_ms_interval in args.sig_ms_intervals:
                logging.debug("adding sig_ms_interval: %s", sig_ms_interval)
                for ledger_chunk_bytes in args.ledger_chunk_bytes:
                    logging.debug("adding ledger_chunk_bytes: %s", ledger_chunk_bytes)
                    for snapshot_tx_interval in args.snapshot_tx_intervals:
                        logging.debug(
                            "adding snapshot_tx_interval: %s", snapshot_tx_interval
                        )
                        lskv_config = Config(
                            store="lskv",
                            port=port,
                            tls=True,
                            sgx=False,
                            worker_threads=worker_threads,
                            sig_tx_interval=sig_tx_interval,
                            sig_ms_interval=sig_ms_interval,
                            ledger_chunk_bytes=ledger_chunk_bytes,
                            snapshot_tx_interval=snapshot_tx_interval,
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


def run(cmd: List[str], name: str, output_dir: str):
    """
    Make a popen object from a command.
    """
    logging.debug("running cmd: %s", cmd)
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

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    bench_dir = os.path.join(BENCH_DIR, benchmark)

    # make the bench directory
    os.makedirs(bench_dir, exist_ok=True)

    configs = make_configurations(args)

    logging.debug("made %d configurations", len(configs))

    for i, config in enumerate(configs):
        if os.path.exists(config.output_dir()):
            logging.warning(
                "skipping config (output dir already exists) %d/%d: %s",
                i + 1,
                len(configs),
                config,
            )
            continue
        os.makedirs(config.output_dir())
        logging.info("executing config %d/%d: %s", i + 1, len(configs), config)
        execute_config(config)

    with cimetrics.upload.metrics():
        pass
