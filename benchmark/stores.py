#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Stores to run benchmarks against.
"""

import json
import os
import shutil
import subprocess
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
                    "--workspace",
                    self.workspace(),
                ]
                if self.config.tmpfs:
                    etcd_cmd.append("--tmpfs")
                for node in self.config.nodes:
                    etcd_cmd.append("--node")
                    etcd_cmd.append(node)
                logger.info("spawning etcd: {}", " ".join(etcd_cmd))
                return Popen(etcd_cmd, stdout=out, stderr=err)

    def workspace(self):
        """
        Return the workspace directory for this store.
        """
        return os.path.join(os.getcwd(), self.config.output_dir(), "workspace")

    def cacert(self) -> str:
        """
        Return the path to the CA certificate.
        """
        return f"{self.workspace()}/certs/ca.pem"

    def cert(self) -> str:
        """
        Return the path to the client certificate.
        """
        return f"{self.workspace()}/certs/client.pem"

    def key(self) -> str:
        """
        Return the path to the key for the client certificate.
        """
        return f"{self.workspace()}/certs/client-key.pem"

    def get_leader_address(self) -> str:
        """
        Get address of the leader node.
        """
        node = self.config.get_node_addr(0)

        command = [
            "bin/etcdctl",
            "--endpoints",
            f"{self.config.scheme()}://{node}",
            "--cacert",
            self.cacert(),
            "--cert",
            self.cert(),
            "--key",
            self.key(),
            "endpoint",
            "status",
            "-w",
            "json",
            "--cluster",
        ]
        logger.debug("Running endpoint status command: {}", command)
        # pylint: disable=subprocess-run-check
        proc = subprocess.run(command, capture_output=True)
        logger.debug("Endpoint status stdout: {}", proc.stdout)
        logger.debug("Endpoint status stderr: {}", proc.stderr)
        json_out = json.loads(proc.stdout)
        logger.debug("Got endpoint status: {}", json_out)

        for element in json_out:
            member_id = element["Status"]["header"]["member_id"]
            leader = element["Status"]["leader"]
            if member_id == leader:
                addr = element["Endpoint"].split("://")[-1]
                logger.info("Found leader node {}", addr)
                return addr

        return node


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
                lskv_cmd = [
                    "benchmark/lskv_cluster.py",
                    "--enclave",
                    self.config.enclave,
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
                    "--http-version",
                    str(self.config.http_version),
                ]

                for node in self.config.nodes:
                    lskv_cmd.append("--node")
                    lskv_cmd.append(node)

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

    def get_leader_address(self) -> str:
        """
        Get address of the leader node.
        """
        node = self.config.get_node_addr(0)

        command = [
            "curl",
            "--cacert",
            self.cacert(),
            "--cert",
            self.cert(),
            "--key",
            self.key(),
            f"{self.config.scheme()}://{node}/node/network/nodes",
        ]
        logger.debug("Running endpoint status command: {}", command)
        # pylint: disable=subprocess-run-check
        proc = subprocess.run(command, capture_output=True)
        logger.debug("Endpoint status stdout: {}", proc.stdout)
        logger.debug("Endpoint status stderr: {}", proc.stderr)
        json_out = json.loads(proc.stdout)
        logger.debug("Got endpoint status: {}", json_out)

        for element in json_out["nodes"]:
            primary = element["primary"]
            if primary:
                addr = element["rpc_interfaces"]["primary_rpc_interface"][
                    "published_address"
                ]
                logger.info("Found leader node {}", addr)
                return addr

        return node
