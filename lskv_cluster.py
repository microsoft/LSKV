# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import time
from subprocess import Popen
from typing import Any, Dict

from loguru import logger


def run(cmd: str, **kwargs) -> subprocess.CompletedProcess:
    logger.debug("Running command: {}", cmd)
    p = subprocess.run(cmd, shell=True, capture_output=True, **kwargs)
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
        cmd = f"curl --silent -X {method} {self.address}{path} --cacert {self.cacert} --key {self.key} --cert {self.cert}"
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
        certs = [
            "--signing-key",
            self.key,
            "--signing-cert",
            self.cert,
        ]
        cmd = (
            f"/opt/ccf_virtual/bin/scurl.sh {self.address}{path} --cacert {self.cacert} "
            + " ".join(certs)
            + f" --header 'content-type: application/json' --data-binary '{json_str}'"
        )
        p = run(cmd)
        out = p.stdout.decode("utf-8")
        if out:
            return json.loads(out)
        return ""


class Operator:
    def __init__(self):
        self.name = "lskv"
        self.nodes = []

    def make_name(self, i: int) -> str:
        return f"{self.name}-{i}"

    def spawn(self) -> Popen:
        name = self.make_name(len(self.nodes))
        cmd = [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-p",
            "8000:8000",
            "lskv-virtual",
        ]
        return Popen(cmd)

    def stop(self):
        for i, _node in enumerate(self.nodes):
            name = self.make_name(i)
            run(f"docker rm -f {name}")

    def copy_certs(self):
        name= self.make_name(0)
        run(f"docker cp {name}:/app/certs/ common", cwd="docker-certs")

        run("/opt/ccf_virtual/bin/keygenerator.sh --name user0", cwd="docker-certs")


class Member:
    def __init__(self, name: str):
        self.name = name
        self.curl = Curl(
            "https://127.0.0.1:8000",
            "docker-certs/common/service_cert.pem",
            f"docker-certs/common/{name}_cert.pem",
            f"docker-certs/common/{name}_privk.pem",
        )
        self.scurl = SCurl(
            "https://127.0.0.1:8000",
            "docker-certs/common/service_cert.pem",
            f"docker-certs/common/{name}_cert.pem",
            f"docker-certs/common/{name}_privk.pem",
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

        logger.info("listing members")
        self.curl.run("GET", "/gov/members")

    def set_user(self):
        set_user = {
            "actions": [
                {
                    "name": "set_user",
                    "args": {
                        "cert": "".join(
                            open("docker-certs/user0_cert.pem", "r").readlines()
                        )
                    },
                }
            ]
        }
        logger.info("creating set_user proposal")
        proposal = self.scurl.run("/gov/proposals", set_user)
        proposal_id = proposal["proposal_id"]

        logger.info("accepting the proposal")
        vote_accept = {
            "ballot": "export function vote (proposal, proposerId) { return true }"
        }
        self.scurl.run(f"/gov/proposals/{proposal_id}/ballots", vote_accept)

    def open_network(self):
        logger.info("Opening the network")
        service_cert = "".join(
            open("docker-certs/common/service_cert.pem", "r").readlines()
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

        logger.info("accepting the proposal")
        vote_accept = {
            "ballot": "export function vote (proposal, proposerId) { return true }"
        }
        self.scurl.run(f"/gov/proposals/{proposal_id}/ballots", vote_accept)


if __name__ == "__main__":
    operator = Operator()
    node = operator.spawn()
    time.sleep(1)
    try:
        shutil.rmtree("docker-certs")
        os.makedirs("docker-certs")

        operator.copy_certs()

        time.sleep(2)

        member0 = Member("member0")

        member0.activate_member()

        member0.set_user()

        member0.open_network()

    except Exception as e:
        logger.info("failed: {}", e)
    finally:
        operator.stop()
