# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#!/usr/bin/env python3

import json
import os
import signal
import subprocess
import time
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
            self.cert
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
            json_str
        ]
        p = run(cmd)
        out = p.stdout.decode("utf-8")
        if out:
            return json.loads(out)
        return ""


class Operator:
    def __init__(self, workspace:str, image:str):
        self.workspace = workspace
        self.name = "lskv"
        self.nodes = 0
        self.image =image

    def make_name(self, i: int) -> str:
        return f"{self.name}-{i}"

    def wait_node(self):
        tries = 60
        i = 0
        while i < tries:
            try:
                run(["curl", "--silent", "-k", "https://127.0.0.1:8000/node/network"])
                break
            except Exception as e:
                logger.warning("Node not ready, try {}: {}", i, e)
            i += 1
            time.sleep(1)


    def add_node(self) :
        name = self.make_name(self.nodes)
        cmd = [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-p",
            "8000:8000",
            self.image
        ]
        run(cmd)
        self.nodes +=1
        self.wait_node()

    def stop_all(self):
        for i in range(self.nodes):
            name = self.make_name(i)
            run(["docker","rm","-f",name])

    def copy_certs(self):
        name= self.make_name(0)
        run(["docker", "cp", f"{name}:/app/certs", "common"], cwd=self.workspace)

        run(["/opt/ccf_virtual/bin/keygenerator.sh", "--name", "user0"], cwd=self.workspace)


class Member:
    def __init__(self, workspace:str,name: str):
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
                    "args": {
                        "cert": "".join(
                            open(cert, "r").readlines()
                        )
                    },
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

    operator = Operator(workspace, "lskv-virtual")
    operator.add_node()
    try:
        operator.copy_certs()

        member0 = Member(workspace,"member0")

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
