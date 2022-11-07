#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

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
    cmd_str = subprocess.list2cmdline(cmd)
    logger.debug("Running command: {}", cmd_str)
    p = subprocess.run(cmd, capture_output=True, **kwargs)
    if p.returncode != 0:
        logger.warning("Command failed, returned {}", p.returncode)
    if p.stdout:
        logger.debug("stdout: {}", p.stdout)
    if p.stderr:
        logger.debug("stderr: {}", p.stderr)
    p.check_returncode()
    return p


class Curl:
    def __init__(self, address: str, cacert: str, cert: str, key: str):
        self.address = address
        self.cacert = cacert
        self.cert = cert
        self.key = key

    def run(self, method: str, path: str) -> Any:
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
        p = run(cmd)
        out = p.stdout.decode("utf-8")
        if out:
            return json.loads(out)
        return ""


class SCurl:
    def __init__(self, address: str, cacert: str, cert: str, key: str):
        self.address = address
        self.cacert = cacert
        self.cert = cert
        self.key = key

    def run(self, path: str, json_data: Dict[str, Any]) -> Any:
        json_str = json.dumps(json_data)
        cmd = [
            f"scurl.sh",
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
        p = run(cmd)
        out = p.stdout.decode("utf-8")
        if out:
            return json.loads(out)
        return ""


@dataclass
class Node:
    index: int
    name: str
    enclave: str
    http_version: int
    # ip address of the first node to connect to
    first_ip: str
    ip: str
    worker_threads:int

    def __post_init__(self):
        base_client_port = 8000
        base_peer_port = 8001
        self.client_port = base_client_port + (2 * self.index)
        self.peer_port = base_peer_port + (2 * self.index)

    def config(self):
        if self.index == 0:
            return self.start_config()
        return self.join_config()

    def start_config(self) -> Dict[str, Any]:
        enclave_file = "/app/liblskv.virtual.so"
        enclave_type = "Virtual"
        if self.enclave == "sgx":
            enclave_file = "/app/liblskv.enclave.so.signed"
            enclave_type = "Release"
        app_protocol = "HTTP1" if self.http_version == 1 else "HTTP2"

        return {
            "enclave": {"file": enclave_file, "type": enclave_type},
            "network": {
                "node_to_node_interface": {
                    "bind_address": f"{self.ip}:{self.peer_port}"
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
        }

    def join_config(self) -> Dict[str, Any]:
        enclave_file = "/app/liblskv.virtual.so"
        enclave_type = "Virtual"
        if self.enclave == "sgx":
            enclave_file = "/app/liblskv.enclave.so.signed"
            enclave_type = "Release"
        app_protocol = "HTTP1" if self.http_version == 1 else "HTTP2"

        base_client_port = 8000
        return {
            "enclave": {"file": enclave_file, "type": enclave_type},
            "network": {
                "node_to_node_interface": {
                    "bind_address": f"{self.ip}:{self.peer_port}"
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
        }


class Operator:
    def __init__(self, workspace: str, image: str, enclave: str, http_version: int, worker_threads:int):
        self.workspace = workspace
        self.name = "lskv"
        self.nodes = []
        self.image = image
        self.enclave = enclave
        self.http_version = http_version
        self.subnet_prefix = "172.20.5"
        self.worker_threads = worker_threads
        self.create_network()

    def create_network(self):
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
        run(["docker", "network", "rm", "lskv"])

    def make_name(self, i: int) -> str:
        return f"{self.name}-{i}"

    def wait_node(self, node: Node):
        tries = 10
        i = 0
        while i < tries:
            try:
                r = run(
                    [
                        "curl",
                        "--silent",
                        "-k",
                        f"https://127.0.0.1:{node.client_port}/node/state",
                    ]
                )
                status = json.loads(r.stdout)["state"]
                if status == "PartOfNetwork":
                    return
            except Exception as e:
                logger.warning("Node not ready, try {}: {}", i, e)
            i += 1
            time.sleep(1)
        raise Exception("Failed to wait for node to be ready")

    def make_node_dir(self, name: str) -> str:
        d = os.path.join(self.workspace, name)
        run(["mkdir", "-p", d])
        return d

    def make_node_config(self, node: Node, node_dir: str) -> str:
        config_file = os.path.join(node_dir, "config.json")

        config = node.config()

        with open(config_file, "w") as f:
            json.dump(config, f)
        return config_file

    def make_node(self) -> Node:
        i = len(self.nodes)
        first_ip = self.first_ip()
        ip = f"{self.subnet_prefix}.{i+1}"
        return Node(
            i,
            name=self.make_name(i),
            enclave=self.enclave,
            http_version=self.http_version,
            first_ip=first_ip,
            ip=ip,
            worker_threads=self.worker_threads,
        )

    def first_ip(self) -> str:
        if len(self.nodes) > 0:
            return self.nodes[0].ip
        return ""

    def add_node(self):
        node = self.make_node()
        node_dir = self.make_node_dir(node.name)
        config_file = self.make_node_config(node, node_dir)
        config_file_abs = os.path.abspath(config_file)
        common_dir_abs = os.path.abspath(os.path.join(self.workspace, "common"))
        constitution_dir_abs = os.path.abspath("constitution")
        cmd = [
            "docker",
            "run",
            "--network",
            "lskv",
            "--ip",
            node.ip,
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
            self.image,
        ]
        run(cmd)
        self.nodes.append(node)
        self.wait_node(node)
        logger.info("Added node {}", node)
        if len(self.nodes) == 1:
            # just made the first node
            self.copy_certs()
        self.list_nodes()

    def list_nodes(self):
        run(["curl", "https://127.0.0.1:8000/node/network/nodes", "--cacert", f"{self.workspace}/common/service_cert.pem"])

    def add_nodes(self, n: int):
        for _ in range(n):
            self.add_node()

    def stop_all(self):
        for node in self.nodes:
            run(["docker", "rm", "-f", node.name])
        self.remove_network()

    def setup_common(self):
        common_dir = os.path.join(self.workspace, "common")
        run(["mkdir", "-p", common_dir])
        run(
            [
                f"keygenerator.sh",
                "--name",
                "member0",
                "--gen-enc-key",
            ],
            cwd=common_dir,
        )
        run(
            [f"keygenerator.sh", "--name", "user0"],
            cwd=common_dir,
        )

    def copy_certs(self):
        name = self.make_name(0)
        run(
            ["docker", "cp", f"{name}:/app/certs/service_cert.pem", "common"],
            cwd=self.workspace,
        )


class Member:
    def __init__(self, workspace: str, name: str ):
        self.workspace = workspace
        self.name = name
        self.curl = Curl(
            "https://127.0.0.1:8000",
            f"{self.workspace}/common/service_cert.pem",
            f"{self.workspace}/common/{name}_cert.pem",
            f"{self.workspace}/common/{name}_privk.pem",
        )
        self.scurl = SCurl(
            "https://127.0.0.1:8000",
            f"{self.workspace}/common/service_cert.pem",
            f"{self.workspace}/common/{name}_cert.pem",
            f"{self.workspace}/common/{name}_privk.pem",
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
        set_user = {
            "actions": [
                {
                    "name": "set_user",
                    "args": {"cert": "".join(open(cert, "r").readlines())},
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
        logger.info("Opening the network")
        service_cert = "".join(
            open(f"{self.workspace}/common/service_cert.pem", "r").readlines()
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

def main(workspace:str,nodes:int, enclave:str, image:str,  http_version:int, worker_threads:int):
    run(["rm", "-rf", workspace])
    run(["mkdir", "-p", workspace])

    operator = Operator(workspace,image,enclave, http_version,  worker_threads)
    try:
        operator.setup_common()
        operator.add_nodes(nodes)

        member0 = Member(workspace, "member0", )

        member0.activate_member()

        member0.set_user(f"{workspace}/common/user0_cert.pem")

        member0.open_network()

        # wait for a signal and print it out
        signals = {signal.SIGINT, signal.SIGTERM}
        # have to set the thread mask: https://bugs.python.org/issue38284
        signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        logger.info("Waiting for a signal")
        sig = signal.sigwait(signals)
        logger.info("Received a signal: {}", signal.Signals(sig).name)

    except Exception as e:
        logger.info("Failed: {}", e)
    finally:
        operator.stop_all()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=str, default="docker-workspace")
    parser.add_argument("--nodes", type=int, default=1)
    parser.add_argument("--enclave", type=str, default="virtual")
    parser.add_argument("--image", type=str, default="lskv-virtual")
    parser.add_argument("--http-version", type=int, default="2")
    parser.add_argument("--worker-threads", type=int, default="0")

    args = parser.parse_args()

    logger.info("Using arguments: {}", args)
    main(args.workspace,args.nodes, args.enclave, args.image,  args.http_version, args.worker_threads)
