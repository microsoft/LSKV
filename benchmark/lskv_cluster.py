#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run a cluster of lskv nodes.
"""

import argparse
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from loguru import logger


def run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """
    Run a command.
    """
    cmd_str = subprocess.list2cmdline(cmd)
    logger.debug("Running command: {}", cmd_str)
    # pylint: disable=subprocess-run-check
    proc = subprocess.run(cmd, capture_output=True, **kwargs)
    if proc.returncode != 0:
        logger.warning("Command failed, returned {}", proc.returncode)
    if proc.stdout:
        logger.debug("stdout: {}", proc.stdout)
    if proc.stderr:
        logger.debug("stderr: {}", proc.stderr)
    proc.check_returncode()
    return proc


# pylint: disable=too-few-public-methods
class Curl:
    """
    Run curl commands.
    """

    def __init__(self, address: str, cacert: str, cert: str, key: str):
        self.address = address
        self.cacert = cacert
        self.cert = cert
        self.key = key

    def run(self, method: str, path: str) -> Any:
        """
        Run a curl invocation.
        """
        cmd = [
            "curl",
            "--silent",
            "-X",
            method,
            f"{self.address}{path}",
            "--cacert",
            self.cacert,
            "--key",
            self.key,
            "--cert",
            self.cert,
        ]
        proc = run(cmd)
        out = proc.stdout.decode("utf-8")
        if out:
            return json.loads(out)
        return ""


# pylint: disable=too-few-public-methods
class SCurl:
    """
    Run SCurl commands.
    """

    def __init__(self, address: str, cacert: str, cert: str, key: str):
        self.address = address
        self.cacert = cacert
        self.cert = cert
        self.key = key

    def run(self, path: str, json_data: Dict[str, Any]) -> Any:
        """
        Run an scurl invocation.
        """
        json_str = json.dumps(json_data)
        cmd = [
            "scurl.sh",
            f"{self.address}{path}",
            "--cacert",
            self.cacert,
            "--signing-key",
            self.key,
            "--signing-cert",
            self.cert,
            "--header",
            "content-type: application/json",
            "--data-binary",
            json_str,
        ]
        proc = run(cmd)
        out = proc.stdout.decode("utf-8")
        if out:
            return json.loads(out)
        return ""


# pylint: disable=too-many-instance-attributes
@dataclass
class Node:
    """
    Config for a node.
    """

    index: int
    name: str
    enclave: str
    http_version: int
    # ip address of the first node to connect to
    first_ip: str
    ip_address: str
    worker_threads: int
    sig_tx_interval: int
    sig_ms_interval: int
    ledger_chunk_bytes: str
    snapshot_tx_interval: int

    def __post_init__(self):
        base_client_port = 8000
        base_peer_port = 8001
        self.client_port = base_client_port + (2 * self.index)
        self.peer_port = base_peer_port + (2 * self.index)

    def config(self):
        """
        Make the config of this node.
        """
        if self.index == 0:
            return self.start_config()
        return self.join_config()

    def start_config(self) -> Dict[str, Any]:
        """
        Make the config of the first node.
        """
        enclave_file = "/app/liblskv.virtual.so"
        enclave_type = "Virtual"
        enclave_platform = "Virtual"
        if self.enclave == "sgx":
            enclave_file = "/app/liblskv.enclave.so.signed"
            enclave_type = "Release"
            enclave_platform = "SGX"
        app_protocol = "HTTP1" if self.http_version == 1 else "HTTP2"

        return {
            "enclave": {
                "file": enclave_file,
                "type": enclave_type,
                "platform": enclave_platform,
            },
            "network": {
                "node_to_node_interface": {
                    "bind_address": f"{self.ip_address}:{self.peer_port}"
                },
                "rpc_interfaces": {
                    "main_interface": {
                        "bind_address": f"0.0.0.0:{self.client_port}",
                        "app_protocol": app_protocol,
                    }
                },
            },
            "node_certificate": {"subject_alt_names": ["iPAddress:127.0.0.1"]},
            "command": {
                "type": "Start",
                "service_certificate_file": "/app/certs/service_cert.pem",
                "start": {
                    "constitution_files": [
                        "/app/constitution/validate.js",
                        "/app/constitution/apply.js",
                        "/app/constitution/resolve.js",
                        "/app/constitution/actions.js",
                    ],
                    "members": [
                        {
                            "certificate_file": "/app/common/member0_cert.pem",
                            "encryption_public_key_file": "/app/common/member0_enc_pubk.pem",
                        }
                    ],
                },
            },
            "worker_threads": self.worker_threads,
            "snapshots": {
                "tx_count": self.snapshot_tx_interval,
            },
            "ledger_signatures": {
                "tx_count": self.sig_tx_interval,
                "delay": f"{self.sig_ms_interval}ms",
            },
            "ledger": {"chunk_size": self.ledger_chunk_bytes},
        }

    def join_config(self) -> Dict[str, Any]:
        """
        Make the config of a joining node.
        """
        enclave_file = "/app/liblskv.virtual.so"
        enclave_type = "Virtual"
        enclave_platform = "Virtual"
        if self.enclave == "sgx":
            enclave_file = "/app/liblskv.enclave.so.signed"
            enclave_type = "Release"
            enclave_platform = "SGX"
        app_protocol = "HTTP1" if self.http_version == 1 else "HTTP2"

        base_client_port = 8000
        return {
            "enclave": {
                "file": enclave_file,
                "type": enclave_type,
                "platform": enclave_platform,
            },
            "network": {
                "node_to_node_interface": {
                    "bind_address": f"{self.ip_address}:{self.peer_port}"
                },
                "rpc_interfaces": {
                    "main_interface": {
                        "bind_address": f"0.0.0.0:{self.client_port}",
                        "app_protocol": app_protocol,
                    }
                },
            },
            "node_certificate": {"subject_alt_names": ["iPAddress:127.0.0.1"]},
            "command": {
                "type": "Join",
                "service_certificate_file": "/app/common/service_cert.pem",
                "join": {
                    "target_rpc_address": f"{self.first_ip}:{base_client_port}",
                },
            },
            "worker_threads": self.worker_threads,
            "snapshots": {
                "tx_count": self.snapshot_tx_interval,
            },
            "ledger_signatures": {
                "tx_count": self.sig_tx_interval,
                "delay": f"{self.sig_ms_interval}ms",
            },
            "ledger": {"chunk_size": self.ledger_chunk_bytes},
        }


# pylint: disable=too-many-instance-attributes
class Operator:
    """
    Operator for a network of nodes.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        workspace: str,
        image: str,
        enclave: str,
        http_version: int,
        worker_threads: int,
        sig_tx_interval: int,
        sig_ms_interval: int,
        ledger_chunk_bytes: str,
        snapshot_tx_interval: int,
    ):
        self.workspace = workspace
        self.name = "lskv"
        self.nodes: List[Node] = []
        self.image = image
        self.enclave = enclave
        self.http_version = http_version
        self.subnet_prefix = "172.20.5"
        self.worker_threads = worker_threads
        self.sig_tx_interval = sig_tx_interval
        self.sig_ms_interval = sig_ms_interval
        self.ledger_chunk_bytes = ledger_chunk_bytes
        self.snapshot_tx_interval = snapshot_tx_interval
        self.create_network()

    def create_network(self):
        """
        Create a Docker network for the nodes.
        """
        run(
            [
                "docker",
                "network",
                "create",
                "--subnet",
                f"{self.subnet_prefix}.0/16",
                "lskv",
            ]
        )

    def remove_network(self):
        """
        Remove the Docker network for the nodes.
        """
        run(["docker", "network", "rm", "lskv"])

    def make_name(self, i: int) -> str:
        """
        Make a name for a node.
        """
        return f"{self.name}-{i}"

    def wait_node(self, node: Node):
        """
        Wait for a node to be ready.
        """
        tries = 10
        i = 0
        while i < tries:
            try:
                proc = run(
                    [
                        "curl",
                        "--silent",
                        "-k",
                        f"https://127.0.0.1:{node.client_port}/node/state",
                    ]
                )
                status = json.loads(proc.stdout)["state"]
                if status == "PartOfNetwork":
                    return
            # pylint: disable=broad-except
            except Exception as exception:
                logger.warning("Node not ready, try {}: {}", i, exception)
            i += 1
            time.sleep(1)
        raise RuntimeError("Failed to wait for node to be ready")

    def make_node_dir(self, name: str) -> str:
        """
        Make a directory for a node's config.
        """
        node_dir = os.path.join(self.workspace, name)
        run(["mkdir", "-p", node_dir])
        return node_dir

    def make_node_config(self, node: Node, node_dir: str) -> str:
        """
        Make the node config file.
        """
        config_file = os.path.join(node_dir, "config.json")

        config = node.config()

        with open(config_file, "w", encoding="utf-8") as config_f:
            json.dump(config, config_f)
        return config_file

    def make_node(self) -> Node:
        """
        Make a node.
        """
        i = len(self.nodes)
        first_ip = self.first_ip()
        ip_address = f"{self.subnet_prefix}.{i+1}"
        return Node(
            i,
            name=self.make_name(i),
            enclave=self.enclave,
            http_version=self.http_version,
            first_ip=first_ip,
            ip_address=ip_address,
            worker_threads=self.worker_threads,
            sig_tx_interval=self.sig_tx_interval,
            sig_ms_interval=self.sig_ms_interval,
            ledger_chunk_bytes=self.ledger_chunk_bytes,
            snapshot_tx_interval=self.snapshot_tx_interval,
        )

    def first_ip(self) -> str:
        """
        Get the IP address of the first node.
        """
        if len(self.nodes) > 0:
            return self.nodes[0].ip_address
        return ""

    def add_node(self):
        """
        Add a node to the network.
        """
        node = self.make_node()
        node_dir = self.make_node_dir(node.name)
        config_file = self.make_node_config(node, node_dir)
        config_file_abs = os.path.abspath(config_file)
        common_dir_abs = os.path.abspath(os.path.join(self.workspace, "sandbox_common"))
        constitution_dir_abs = os.path.abspath("constitution")
        cmd = [
            "docker",
            "run",
            "--network",
            "lskv",
            "--ip",
            node.ip_address,
            "--rm",
            "-d",
            "--name",
            node.name,
            "-p",
            f"{node.client_port}:{node.client_port}",
            "-v",
            f"{config_file_abs}:/app/config/config.json:ro",
            "-v",
            f"{common_dir_abs}:/app/common:ro",
            "-v",
            f"{constitution_dir_abs}:/app/constitution:ro",
        ]
        if self.enclave == "sgx":
            cmd += [
                "--device",
                "/dev/sgx_enclave:/dev/sgx_enclave",
                "--device",
                "/dev/sgx_provision:/dev/sgx_provision",
                "-v",
                "/dev/sgx:/dev/sgx",
            ]
            self.image += "-sgx"
        else:
            self.image += "-virtual"
        cmd.append(self.image)
        run(cmd)
        self.nodes.append(node)
        self.wait_node(node)
        logger.info("Added node {}", node)
        if len(self.nodes) == 1:
            # just made the first node
            self.copy_certs()
        self.list_nodes()

    def list_nodes(self):
        """
        List the nodes in the network.
        """
        run(
            [
                "curl",
                "https://127.0.0.1:8000/node/network/nodes",
                "--cacert",
                f"{self.workspace}/sandbox_common/service_cert.pem",
            ]
        )

    def add_nodes(self, num: int):
        """
        Add multiple nodes to the network.
        """
        for _ in range(num):
            self.add_node()

    def stop_all(self):
        """
        Stop all nodes in the network and remove the network.
        """
        for node in self.nodes:
            run(["docker", "rm", "-f", node.name])
        self.remove_network()

    def setup_common(self):
        """
        Set up the common directory for shared information.
        """
        common_dir = os.path.join(self.workspace, "sandbox_common")
        run(["mkdir", "-p", common_dir])
        run(
            [
                "keygenerator.sh",
                "--name",
                "member0",
                "--gen-enc-key",
            ],
            cwd=common_dir,
        )
        run(
            ["keygenerator.sh", "--name", "user0"],
            cwd=common_dir,
        )

    def copy_certs(self):
        """
        Copy certificates from the first node to the common directory.
        """
        name = self.make_name(0)
        run(
            ["docker", "cp", f"{name}:/app/certs/service_cert.pem", "sandbox_common"],
            cwd=self.workspace,
        )


class Member:
    """
    A governance member.
    """

    def __init__(self, workspace: str, name: str):
        self.workspace = workspace
        self.name = name
        self.curl = Curl(
            "https://127.0.0.1:8000",
            f"{self.workspace}/sandbox_common/service_cert.pem",
            f"{self.workspace}/sandbox_common/{name}_cert.pem",
            f"{self.workspace}/sandbox_common/{name}_privk.pem",
        )
        self.scurl = SCurl(
            "https://127.0.0.1:8000",
            f"{self.workspace}/sandbox_common/service_cert.pem",
            f"{self.workspace}/sandbox_common/{name}_cert.pem",
            f"{self.workspace}/sandbox_common/{name}_privk.pem",
        )

    def activate_member(self):
        """
        Activate a member in the network.
        """
        logger.info("Activating {}", self.name)

        logger.info("Listing members")
        self.curl.run("GET", "/gov/members")

        logger.info("Getting latest state digest")
        state_digest = self.curl.run("POST", "/gov/ack/update_state_digest")

        logger.info("Signing and returning the state digest")
        self.scurl.run("/gov/ack", state_digest)

        logger.info("Listing members")
        self.curl.run("GET", "/gov/members")

    def set_user(self, cert: str):
        """
        Set a new user in the network through governance.
        """
        # pylint: disable=consider-using-with
        cert = "".join(open(cert, "r", encoding="utf-8").readlines())
        set_user = {
            "actions": [
                {
                    "name": "set_user",
                    "args": {"cert": cert},
                }
            ]
        }
        logger.info("Creating set_user proposal")
        proposal = self.scurl.run("/gov/proposals", set_user)
        proposal_id = proposal["proposal_id"]

        logger.info("Accepting the proposal")
        vote_accept = {
            "ballot": "export function vote (proposal, proposerId) { return true }"
        }
        self.scurl.run(f"/gov/proposals/{proposal_id}/ballots", vote_accept)

    def open_network(self):
        """
        Open the network for users
        """
        logger.info("Opening the network")
        # pylint: disable=consider-using-with
        service_cert = "".join(
            open(
                f"{self.workspace}/sandbox_common/service_cert.pem",
                "r",
                encoding="utf-8",
            ).readlines()
        )
        transition_service_to_open = {
            "actions": [
                {
                    "name": "transition_service_to_open",
                    "args": {
                        "next_service_identity": service_cert,
                    },
                }
            ]
        }
        proposal = self.scurl.run("/gov/proposals", transition_service_to_open)
        proposal_id = proposal["proposal_id"]

        logger.info("Accepting the proposal")
        vote_accept = {
            "ballot": "export function vote (proposal, proposerId) { return true }"
        }
        self.scurl.run(f"/gov/proposals/{proposal_id}/ballots", vote_accept)

        logger.info("Network is now open to users!")


# pylint: disable=too-many-arguments
def main(
    workspace: str,
    nodes: int,
    enclave: str,
    image: str,
    http_version: int,
    worker_threads: int,
    sig_tx_interval: int,
    sig_ms_interval: int,
    ledger_chunk_bytes: str,
    snapshot_tx_interval: int,
):
    """
    Main entry point.
    """
    run(["rm", "-rf", workspace])
    run(["mkdir", "-p", workspace])

    operator = Operator(
        workspace,
        image,
        enclave,
        http_version,
        worker_threads,
        sig_tx_interval,
        sig_ms_interval,
        ledger_chunk_bytes,
        snapshot_tx_interval,
    )
    try:
        operator.setup_common()
        operator.add_nodes(nodes)

        member0 = Member(
            workspace,
            "member0",
        )

        member0.activate_member()

        member0.set_user(f"{workspace}/sandbox_common/user0_cert.pem")

        member0.open_network()

        # wait for a signal and print it out
        signals = {signal.SIGINT, signal.SIGTERM}
        # have to set the thread mask: https://bugs.python.org/issue38284
        signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        logger.info("Waiting for a signal")
        sig = signal.sigwait(signals)
        logger.info("Received a signal: {}", signal.Signals(sig).name)

    # pylint: disable=broad-except
    except Exception as exception:
        logger.info("Failed: {}", exception)
    finally:
        operator.stop_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=str, default="workspace")
    parser.add_argument("--nodes", type=int, default=1)
    parser.add_argument("--enclave", type=str, default="virtual")
    parser.add_argument(
        "--image", type=str, default="lskv:latest"
    )
    parser.add_argument("--http-version", type=int, default="2")
    parser.add_argument("--worker-threads", type=int, default="0")
    parser.add_argument("--sig-tx-interval", type=int, default="5000")
    parser.add_argument("--sig-ms-interval", type=int, default="1000")
    parser.add_argument("--ledger-chunk-bytes", type=str, default="5MB")
    parser.add_argument("--snapshot-tx-interval", type=int, default="10000")

    args = parser.parse_args()

    logger.info("Using arguments: {}", args)
    main(
        args.workspace,
        args.nodes,
        args.enclave,
        args.image,
        args.http_version,
        args.worker_threads,
        args.sig_tx_interval,
        args.sig_ms_interval,
        args.ledger_chunk_bytes,
        args.snapshot_tx_interval,
    )
