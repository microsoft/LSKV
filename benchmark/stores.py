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
                package = "build/liblskv"
                if self.config.enclave == "sgx":
                    package += ".enclave.so.signed"
                else:
                    package += ".virtual.so"
                lskv_cmd = [
                    f"/opt/ccf_{self.config.enclave}/bin/sandbox.sh",
                    "--enclave-type",
                    "virtual" if self.config.enclave == "virtual" else "release",
                    "--package",
                    package,
                    "--verbose",
                    "--worker-threads",
                    str(self.config.worker_threads),
                    "--sig-tx-interval",
                    str(self.config.sig_tx_interval),
                    "--sig-ms-interval",
                    str(self.config.sig_ms_interval),
                    "--ledger-chunk-bytes",
                    self.config.ledger_chunk_bytes,
                    "--snapshot-tx-interval",
                    str(self.config.snapshot_tx_interval),
                    "--workspace",
                    self.workspace(),
                ]
                if self.config.http_version == 2:
                    lskv_cmd.append("--http2")

                port = 8000
                for i in range(self.config.nodes):
                    lskv_cmd.append("--node")
                    lskv_cmd.append(f"local://127.0.0.1:{port + i}")
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
