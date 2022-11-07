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
                ccf_prefix = "/opt/ccf"
                image = "lskv-"
                if self.config.sgx:
                    ccf_prefix += "_sgx"
                    image += "sgx"
                else:
                    ccf_prefix += "_virtual"
                    image += "virtual"
                lskv_cmd = [
                    "benchmark/lskv_cluster.py",
                    "--nodes",
                    str(self.config.nodes),
                    "--enclave",
                    "sgx" if self.config.sgx else "virtual",
                    "--image",
                    image,
                    "--ccf-bin-dir",
                    f"{ccf_prefix}/bin",
                    "--worker-threads",
                    str(self.config.worker_threads),
                    "--http-version",
                    str(self.config.http_version),
                    "--workspace",
                    self.workspace(),
                ]
                logger.info("spawning lskv: {}", lskv_cmd)
                return Popen(lskv_cmd, stdout=out, stderr=err)

    def workspace(self):
        """
        Return the workspace directory for this store.
        """
        return os.path.join(os.getcwd(), self.config.output_dir(), "workspace")

    def cacert(self) -> str:
        """
        Return the path to the CA certificate.
        """
        return f"{self.workspace()}/common/service_cert.pem"

    def cert(self) -> str:
        """
        Return the path to the client certificate.
        """
        return f"{self.workspace()}/common/user0_cert.pem"

    def key(self) -> str:
        """
        Return the path to the key for the client certificate.
        """
        return f"{self.workspace()}/common/user0_privk.pem"
