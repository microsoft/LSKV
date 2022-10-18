#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Common module for benchmark utils.
"""

import logging
import os
from typing import List
import abc
import time
from subprocess import Popen
import typing_extensions


class Config(abc.ABC):
    """
    Store of config to setup and run a benchmark instance.
    """

    def output_dir(self) -> str:
        """
        Return the output directory for this datastore.
        """
        out_dir = os.path.join(self.bench_dir(), self.to_str())
        if not os.path.exists(out_dir):
            logging.info("creating output dir: %s", out_dir)
            os.makedirs(out_dir)
        return out_dir

    @abc.abstractmethod
    def to_str(self) -> str:
        """
        Return the string representation of this config.
        """
        raise NotImplementedError

    def bench_dir(self) -> str:
        """
        Return the benchmark directory.
        """
        return "bench"


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

    @abc.abstractmethod
    def name(self) -> str:
        """
        Get the name of the benchmark.
        """
        raise NotImplementedError


# want runs to take a limited number of seconds if they can handle the rate
DESIRED_DURATION_S = 20

def wait_with_timeout(process: Popen, duration_seconds=2 * DESIRED_DURATION_S, name=""):
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