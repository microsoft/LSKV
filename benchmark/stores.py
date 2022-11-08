#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Stores to run benchmarks against.
"""

import os
import shutil
from subprocess import Popen

from common import Store
from loguru import logger


class EtcdStore(Store):
    """
    A store based on etcd.
    """

    def spawn(self) -> Popen:
        with open(
            os.path.join(self.config.output_dir(), "node.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(self.config.output_dir(), "node.err"),
                "w",
                encoding="utf-8",
            ) as err:
                etcd_cmd = [
                    "benchmark/etcd_cluster.py",
                    "--scheme",
                    self.config.scheme(),
                    "--nodes",
                    str(self.config.nodes),
                ]
                logger.info("spawning etcd: {}", etcd_cmd)
                return Popen(etcd_cmd, stdout=out, stderr=err)

    def cacert(self) -> str:
        """
        Return the path to the CA certificate.
        """
        return "certs/ca.pem"

    def cert(self) -> str:
        """
        Return the path to the client certificate.
        """
        return "certs/client.pem"

    def key(self) -> str:
        """
        Return the path to the key for the client certificate.
        """
        return "certs/client-key.pem"

    def cleanup(self):
        shutil.rmtree("default.etcd", ignore_errors=True)


class LSKVStore(Store):
    """
    A store based on LSKV.
    """

    def spawn(self) -> Popen:
        with open(
            os.path.join(self.config.output_dir(), "node.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(self.config.output_dir(), "node.err"),
                "w",
                encoding="utf-8",
            ) as err:
                libargs = ["build/liblskv.virtual.so"]
                if self.config.sgx:
                    libargs = ["build/liblskv.enclave.so.signed", "-e", "release"]
                env = os.environ.copy()
                env["VENV_DIR"] = os.path.join(os.getcwd(), ".venv")
                nodes = []
                for i in range(self.config.nodes):
                    nodes += ["--node", f"local://127.0.0.1:{self.config.port+i}"]
                ccf_prefix = "/opt/ccf"
                if self.config.sgx:
                    ccf_prefix += "_sgx"
                else:
                    ccf_prefix += "_virtual"
                kvs_cmd = (
                    [f"{ccf_prefix}/bin/sandbox.sh", "-p"]
                    + libargs
                    + [
                        "--worker-threads",
                        str(self.config.worker_threads),
                        "--workspace",
                        self.workspace(),
                        "--verbose",
                    ]
                    + nodes
                )
                if self.config.http_version == 2:
                    kvs_cmd += ["--http2"]
                logger.info("spawning lskv: {}", kvs_cmd)
                return Popen(kvs_cmd, stdout=out, stderr=err, env=env)

    def workspace(self):
        """
        Return the workspace directory for this store.
        """
        return os.path.join(os.getcwd(), self.config.output_dir(), "workspace")

    def cacert(self) -> str:
        """
        Return the path to the CA certificate.
        """
        return f"{self.workspace()}/sandbox_common/service_cert.pem"

    def cert(self) -> str:
        """
        Return the path to the client certificate.
        """
        return f"{self.workspace()}/sandbox_common/user0_cert.pem"

    def key(self) -> str:
        """
        Return the path to the key for the client certificate.
        """
        return f"{self.workspace()}/sandbox_common/user0_privk.pem"
