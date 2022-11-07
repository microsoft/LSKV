# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#!/usr/bin/env python3

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
            "/opt/ccf_virtual/bin/scurl.sh",
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
    name:str
    enclave :str

    def __post_init__(self):
        base_client_port = 8000
        base_peer_port = 8001
        self.client_port = base_client_port + (2 * self.index)
        self.peer_port = base_peer_port + (2 * self.index)


    def start_config(self)->Dict[str, Any]:
        enclave_file = "/app/liblskv.virtual.so"
        enclave_type = "Virtual"
        if self.enclave == "sgx":
            enclave_file = "/app/liblskv.enclave.so.signed"
            enclave_type = "Release"

        return {
            "enclave": {"file":enclave_file, "type":enclave_type},
            "network": {
                "node_to_node_interface": {"bind_address": f"127.0.0.1:{self.peer_port}"},
                "rpc_interfaces": {
                    "main_interface": {
                        "bind_address": f"0.0.0.0:{self.client_port}",
                        "app_protocol": "HTTP2",
                    }
                },
            },
            "node_certificate": {"subject_alt_names": ["iPAddress:127.0.0.1"]},
            "command": {
                "type": "Start",
                "service_certificate_file": "/app/certs/service_cert.pem",
                "start": {
                    "constitution_files": [
                        "/app/validate.js",
                        "/app/apply.js",
                        "/app/resolve.js",
                        "/app/actions.js",
                    ],
                    "members": [
                        {
                            "certificate_file": "/app/certs/member0_cert.pem",
                            "encryption_public_key_file": "/app/certs/member0_enc_pubk.pem",
                        }
                    ],
                },
            },
        }

class Operator:
    def __init__(self, workspace: str, image: str, enclave : str):
        self.workspace = workspace
        self.name = "lskv"
        self.nodes = []
        self.image = image
        self.enclave = enclave

    def make_name(self, i: int) -> str:
        return f"{self.name}-{i}"

    def wait_node(self, node : Node):
        tries = 60
        i = 0
        while i < tries:
            try:
                run(["curl", "--silent", "-k", f"https://127.0.0.1:{node.client_port}/node/network"])
                break
            except Exception as e:
                logger.warning("Node not ready, try {}: {}", i, e)
            i += 1
            time.sleep(1)

    def make_node_dir(self, name: str) -> str:
        d = os.path.join(self.workspace, name)
        run(["mkdir", "-p", d])
        return d

    def make_node_config(self,node:Node, node_dir: str) -> str:
        config_file = os.path.join(node_dir, "config.json")

        # TODO: just start nodes for now
        config = node.start_config()

        with open(config_file, "w") as f:
            json.dump(config, f)
        return config_file

    def make_node(self)->Node:
        i = len(self.nodes)
        return Node(i, name=self.make_name(i), enclave=self.enclave)

    def add_node(self):
        node = self.make_node()
        node_dir = self.make_node_dir(node.name)
        config_file = self.make_node_config(node, node_dir)
        config_file_abs = os.path.abspath(config_file)
        cmd = [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            node.name,
            "-p",
           f"{node.client_port}:{node.client_port}",
            "-v",
            f"{config_file_abs}:/app/config.json",
            self.image,
        ]
        run(cmd)
        self.wait_node(node)
        self.nodes.append( node)

    def stop_all(self):
        for node in self.nodes:
            run(["docker", "rm", "-f", node.name])

    def copy_certs(self):
        name = self.make_name(0)
        run(["docker", "cp", f"{name}:/app/certs", "common"], cwd=self.workspace)

        run(
            ["/opt/ccf_virtual/bin/keygenerator.sh", "--name", "user0"],
            cwd=self.workspace,
        )


class Member:
    def __init__(self, workspace: str, name: str):
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


if __name__ == "__main__":
    workspace = "docker-workspace"

    run(["rm", "-rf", workspace])
    run(["mkdir", "-p", workspace])

    operator = Operator(workspace, "lskv-virtual", "virtual")
    operator.add_node()
    try:
        operator.copy_certs()

        member0 = Member(workspace, "member0")

        member0.activate_member()

        member0.set_user(f"{workspace}/user0_cert.pem")

        member0.open_network()

        # wait for a signal and print it out
        signals = {signal.SIGINT, signal.SIGTERM}
        logger.info("Waiting for a signal")
        sig = signal.sigwait(signals)
        logger.info("Received a signal: {}", signal.Signals(sig).name)

    except Exception as e:
        logger.info("Failed: {}", e)
    finally:
        operator.stop_all()
