#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Stores to run benchmarks against.
"""

import logging
import os
import shutil
from subprocess import Popen

from common import Store


class EtcdStore(Store):
    """
    A store based on etcd.
    """

    def spawn(self) -> Popen:
        logging.debug("spawning etcd")
        client_urls = f"{self.config.scheme()}://127.0.0.1:{self.config.port}"
        with open(
            os.path.join(self.config.output_dir(), "node.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(self.config.output_dir(), "node.err"),
                "w",
                encoding="utf-8",
            ) as err:
                etcd_cmd = [
                    "bin/etcd",
                    "--listen-client-urls",
                    client_urls,
                    "--advertise-client-urls",
                    client_urls,
                ]
                if self.config.tls:
                    etcd_cmd += [
                        "--cert-file",
                        "certs/server.pem",
                        "--key-file",
                        "certs/server-key.pem",
                        "--trusted-ca-file",
                        "certs/ca.pem",
                    ]
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
                kvs_cmd = (
                    ["/opt/ccf/bin/sandbox.sh", "-p"]
                    + libargs
                    + [
                        "--worker-threads",
                        str(self.config.worker_threads),
                        "--workspace",
                        self.workspace(),
                        "--node",
                        f"local://127.0.0.1:{self.config.port}",
                        "--verbose",
                    ]
                )
                if self.config.http2:
                    kvs_cmd += ["--http2"]
                logging.info("spawning lskv %s", kvs_cmd)
                return Popen(kvs_cmd, stdout=out, stderr=err)

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
