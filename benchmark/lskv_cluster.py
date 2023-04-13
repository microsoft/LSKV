#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run a cluster of lskv nodes.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import paramiko
from loguru import logger


class Runner:
    """
    Class to manage running nodes.
    """

    address: str

    def __init__(self, address: str):
        self.address = address

    def copy_file(self, _src: str, _dst: str):
        """
        Copy a file.
        """
        raise NotImplementedError("copy_file not implemented.")

    def create_dir(self, _dst: str):
        """
        Copy a file.
        """
        raise NotImplementedError("create_dir not implemented.")

    def run(self, cmd: str):
        """
        Run a command.
        """
        raise NotImplementedError("run not implemented.")

    def spawn(self, cmd: str):
        """
        Spawn a command.
        """
        raise NotImplementedError("spawn not implemented.")


class LocalRunner(Runner):
    """
    Run a local node.
    """

    def copy_file(self, src: str, dst: str):
        """
        Copy a file.
        """
        logger.info("[{}] Copying file from {} to {}", self.address, src, dst)
        shutil.copy(src, dst)

    def create_dir(self, dst: str):
        """
        Create a directory.
        """
        logger.info("[{}] Creating directory", self.address, dst)
        os.makedirs(dst, exist_ok=True)

    def run(self, cmd: str):
        logger.info("[{}] Running command '{}'", self.address, cmd)
        subprocess.run(cmd, check=True, shell=True)

    def spawn(self, cmd: str):
        logger.info("[{}] Spawning command '{}'", self.address, cmd)
        subprocess.Popen(cmd, shell=True)


class RemoteRunner(Runner):
    """
    Run a node on a remote machine.
    """

    def __init__(self, username: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(self.address, username=username)

        self.client = client

        self.session = self.client.open_sftp()

    def copy_file(self, src: str, dst: str):
        """
        Copy a file.
        """
        logger.info("[{}] Copying file from {} to {}", self.address, src, dst)
        self.session.put(src, dst)
        stat = os.stat(src)
        self.session.chmod(dst, stat.st_mode)

    def create_dir(self, dst: str):
        """
        Create a directory.
        """
        logger.info("[{}] Creating directory {}", self.address, dst)
        _, stdout, _ = self.client.exec_command(f"mkdir -p {dst}")
        stdout.channel.recv_exit_status()

    def run(self, cmd: str):
        logger.info("[{}] Running command '{}'", self.address, cmd)
        _, stdout, _ = self.client.exec_command(cmd)
        stdout.channel.recv_exit_status()

    def spawn(self, cmd: str):
        logger.info("[{}] Spawning command '{}'", self.address, cmd)
        self.client.exec_command(cmd)


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

    def run(self, method: str, path: str, data=None, content_type=None) -> Any:
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
        if data:
            cmd += ["--data-binary", data]
        if content_type:
            cmd += ["--header", f"content-type: {content_type}"]
        proc = run(cmd)
        out = proc.stdout.decode("utf-8")
        if out:
            return json.loads(out)
        return ""

    def sign_and_send(
        self, path: str, message_type: str, data: Any, proposal_id=None
    ) -> Any:
        """
        Sign some data and post it.
        """
        date_proc = run(["date", "-Is"])
        date = date_proc.stdout.decode("utf-8").strip()

        with tempfile.NamedTemporaryFile(mode="w+") as data_file:
            json.dump(data, data_file)
            data_file.flush()

            cmd = [
                "ccf_cose_sign1",
                "--ccf-gov-msg-type",
                message_type,
                "--ccf-gov-msg-created_at",
                date,
                "--signing-cert",
                self.cert,
                "--signing-key",
                self.key,
                "--content",
                data_file.name,
            ]
            if proposal_id:
                cmd += ["--ccf-gov-msg-proposal_id", proposal_id]
            signed_proc = run(cmd)

        with tempfile.NamedTemporaryFile(mode="wb+") as signed_data_file:
            signed_data_file.write(signed_proc.stdout)
            signed_data_file.flush()

            logger.info("Returning the signed data")
            return self.run(
                "POST",
                path,
                data=f"@{signed_data_file.name}",
                content_type="application/cose",
            )


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
    client_port: int
    worker_threads: int
    sig_tx_interval: int
    sig_ms_interval: int
    ledger_chunk_bytes: str
    snapshot_tx_interval: int

    # to be able to work with it
    runner: Runner

    def __post_init__(self):
        self.peer_port = self.client_port + 1

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
                    "primary_rpc_interface": {
                        "bind_address": f"0.0.0.0:{self.client_port}",
                        "published_address": f"{self.ip_address}:{self.client_port}",
                        "app_protocol": app_protocol,
                    }
                },
            },
            "node_certificate": {"subject_alt_names": [f"iPAddress:{self.ip_address}"]},
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
                    "primary_rpc_interface": {
                        "bind_address": f"0.0.0.0:{self.client_port}",
                        "published_address": f"{self.ip_address}:{self.client_port}",
                        "app_protocol": app_protocol,
                    }
                },
            },
            "node_certificate": {"subject_alt_names": [f"iPAddress:{self.ip_address}"]},
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
        if enclave == "sgx":
            self.image += "-sgx"
        else:
            self.image += "-virtual"
        self.enclave = enclave
        self.http_version = http_version
        self.worker_threads = worker_threads
        self.sig_tx_interval = sig_tx_interval
        self.sig_ms_interval = sig_ms_interval
        self.ledger_chunk_bytes = ledger_chunk_bytes
        self.snapshot_tx_interval = snapshot_tx_interval

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
                        f"https://{node.ip_address}:{node.client_port}/node/state",
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

    def make_node_dir(self, name: str, runner: Runner) -> str:
        """
        Make a directory for a node's config.
        """
        node_dir = os.path.join(self.workspace, name)
        runner.create_dir(node_dir)
        os.makedirs(node_dir, exist_ok=True)
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

    def make_node(self, address: str, runner: Runner) -> Node:
        """
        Make a node.
        """
        i = len(self.nodes)
        first_ip = self.first_ip()
        ip_address_port = address.split("://")[1].split(":")
        ip_address = ip_address_port[0]
        port = int(ip_address_port[1])
        return Node(
            i,
            name=self.make_name(i),
            enclave=self.enclave,
            http_version=self.http_version,
            first_ip=first_ip,
            ip_address=ip_address,
            client_port=port,
            worker_threads=self.worker_threads,
            sig_tx_interval=self.sig_tx_interval,
            sig_ms_interval=self.sig_ms_interval,
            ledger_chunk_bytes=self.ledger_chunk_bytes,
            snapshot_tx_interval=self.snapshot_tx_interval,
            runner=runner,
        )

    def first_ip(self) -> str:
        """
        Get the IP address of the first node.
        """
        if len(self.nodes) > 0:
            return self.nodes[0].ip_address
        return ""

    def first_port(self) -> int:
        """
        Get the IP address of the first node.
        """
        if len(self.nodes) > 0:
            return self.nodes[0].client_port
        return 0

    def add_node(self, address: str, runner: Runner):
        """
        Add a node to the network.
        """
        node = self.make_node(address, runner)
        node_dir = self.make_node_dir(node.name, node.runner)
        node_dir_abs = os.path.abspath(node_dir)
        config_file = self.make_node_config(node, node_dir)
        config_file_abs = os.path.abspath(config_file)

        runner.create_dir(os.path.join(node_dir, "common"))
        for file in ["member0_cert.pem", "member0_enc_pubk.pem"] + (
            ["service_cert.pem"] if self.nodes else []
        ):
            src = os.path.join(self.workspace, "common", file)
            dst = os.path.join(node_dir, "common", os.path.basename(file))
            runner.copy_file(src, dst)
        common_dir_abs = os.path.join(node_dir_abs, "common")

        runner.create_dir(os.path.join(node_dir, "constitution"))
        for file in ["actions.js", "apply.js", "resolve.js", "validate.js"]:
            src = os.path.join("constitution", file)
            dst = os.path.join(node_dir, "constitution", os.path.basename(file))
            runner.copy_file(src, dst)
        constitution_dir_abs = os.path.join(node_dir_abs, "constitution")

        runner.run(f"docker rm -f {node.name}")

        # copy file over
        docker_file = os.path.join(self.workspace, "common", "lskv-docker.tar.gz")
        src = os.path.abspath(docker_file)
        dst = os.path.join(node_dir, os.path.basename(docker_file))
        runner.copy_file(src, dst)
        # load docker image on other end
        runner.run(f"docker load -i {dst}")

        cmd = [
            "docker",
            "run",
            "--network",
            "host",
            "--rm",
            "--name",
            node.name,
            "-v",
            f"{config_file_abs}:/app/config/config.json:ro",
            "-v",
            f"{common_dir_abs}:/app/common:ro",
        ]
        if not self.nodes:
            cmd += [
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
        cmd.append(self.image)
        cmd_str = subprocess.list2cmdline(cmd)
        cmd_str = f"cd {node_dir_abs} && {cmd_str} >out 2>err"
        runner.spawn(cmd_str)
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
        first_node = self.nodes[0]
        run(
            [
                "curl",
                f"https://{first_node.ip_address}:{first_node.client_port}/node/network/nodes",
                "--cacert",
                f"{self.workspace}/common/service_cert.pem",
            ]
        )

    def add_nodes(self, addresses: List[str], runners: List[Runner]):
        """
        Add multiple nodes to the network.
        """
        for (address, runner) in zip(addresses, runners):
            self.add_node(address, runner)

    def stop_all(self):
        """
        Stop all nodes in the network and remove the network.
        """
        logger.info("Stopping all nodes")
        for node in self.nodes:
            logger.info("Stopping {}", node.name)
            node.runner.run(f"docker rm -f {node.name}")

    def setup_common(self):
        """
        Set up the common directory for shared information.
        """
        common_dir = os.path.join(self.workspace, "common")
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

        docker_file = os.path.join(self.workspace, "common", "lskv-docker.tar.gz")
        # make sure we have the image locally
        logger.info("Checking if image {} exists", self.image)
        res = subprocess.run(
            ["docker", "image", "inspect", self.image], stdout=subprocess.DEVNULL
        )
        if res.returncode:
            logger.info("Pulling image {}", self.image)
            subprocess.run(["docker", "pull", self.image], check=True)
        else:
            logger.info("Image {} exists locally", self.image)
        # save image to file
        logger.info("Saving image {} to file {}", self.image, docker_file)
        subprocess.run(
            f"docker save {self.image} | gzip > {docker_file}",
            check=True,
            shell=True,
        )

    def copy_certs(self):
        """
        Copy certificates from the first node to the common directory.
        """
        name = self.make_name(0)
        run(
            ["docker", "cp", f"{name}:/app/certs/service_cert.pem", "common"],
            cwd=self.workspace,
        )


class Member:
    """
    A governance member.
    """

    def __init__(self, workspace: str, name: str, ip_address: str, port: int):
        self.workspace = workspace
        self.name = name
        self.public_key = f"{self.workspace}/sandbox_common/{name}_cert.pem"
        self.private_key = f"{self.workspace}/sandbox_common/{name}_privk.pem"
        self.curl = Curl(
            f"https://{ip_address}:{port}",
            f"{self.workspace}/sandbox_common/service_cert.pem",
            self.public_key,
            self.private_key,
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

        logger.info("Signing the state digest")
        logger.info(state_digest)
        self.curl.sign_and_send("/gov/ack", "ack", state_digest)

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
        proposal = self.curl.sign_and_send("/gov/proposals", "proposal", set_user)
        proposal_id = proposal["proposal_id"]

        logger.info("Accepting the proposal")
        vote_accept = {
            "ballot": "export function vote (proposal, proposerId) { return true }"
        }
        self.curl.sign_and_send(
            f"/gov/proposals/{proposal_id}/ballots",
            "ballot",
            vote_accept,
            proposal_id=proposal_id,
        )

    def open_network(self):
        """
        Open the network for users
        """
        logger.info("Opening the network")
        # pylint: disable=consider-using-with
        service_cert = "".join(
            open(
                f"{self.workspace}/common/service_cert.pem",
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
        proposal = self.curl.sign_and_send(
            "/gov/proposals", "proposal", transition_service_to_open
        )
        proposal_id = proposal["proposal_id"]

        logger.info("Accepting the proposal")
        vote_accept = {
            "ballot": "export function vote (proposal, proposerId) { return true }"
        }
        self.curl.sign_and_send(
            f"/gov/proposals/{proposal_id}/ballots",
            "ballot",
            vote_accept,
            proposal_id=proposal_id,
        )

        logger.info("Network is now open to users!")


# pylint: disable=too-many-arguments
def main(
    workspace: str,
    nodes: List[str],
    enclave: str,
    image: str,
    http_version: int,
    worker_threads: int,
    sig_tx_interval: int,
    sig_ms_interval: int,
    ledger_chunk_bytes: str,
    snapshot_tx_interval: int,
    runners: List[Runner],
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
        operator.add_nodes(nodes, runners)

        member0 = Member(
            workspace, "member0", operator.first_ip(), operator.first_port()
        )

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

    # pylint: disable=broad-except
    except Exception as exception:
        logger.info("Failed: {}", exception)
    finally:
        operator.stop_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=str, default="workspace")
    parser.add_argument(
        "--node",
        action="extend",
        nargs="+",
        type=str,
        help="The nodes to launch in the form local://ip:port or ssh://ip:port",
    )
    parser.add_argument("--enclave", type=str, default="virtual")
    parser.add_argument("--image", type=str, default="lskv:latest")
    parser.add_argument("--http-version", type=int, default="2")
    parser.add_argument("--worker-threads", type=int, default="0")
    parser.add_argument("--sig-tx-interval", type=int, default="5000")
    parser.add_argument("--sig-ms-interval", type=int, default="1000")
    parser.add_argument("--ledger-chunk-bytes", type=str, default="5MB")
    parser.add_argument("--snapshot-tx-interval", type=int, default="10000")

    parser.add_argument("--ssh-user", type=str, default="")

    args = parser.parse_args()

    if not args.node:
        parser.error("must have at least one node to run")

    node_addresses_full = [n.split("://") for n in args.node]
    prefixes = list({n[0] for n in node_addresses_full})
    if len(prefixes) != 1:
        parser.error("nodes should all have the same prefix")

    node_addresses = [
        (n[1].split(":")[0], int(n[1].split(":")[1])) for n in node_addresses_full
    ]
    logger.info("Made addresses {}", node_addresses)

    if prefixes[0] == "local":
        logger.info("Using local")
        runners = [LocalRunner(f"{ip}:{port}") for (ip, port) in node_addresses]
    elif prefixes[0] == "ssh":
        logger.info("Using ssh")
        runners = [RemoteRunner(args.ssh_user, ip) for (ip, _port) in node_addresses]
    else:
        parser.error("Found unexpected prefix")

    logger.info("Using arguments: {}", args)
    main(
        args.workspace,
        args.node,
        args.enclave,
        args.image,
        args.http_version,
        args.worker_threads,
        args.sig_tx_interval,
        args.sig_ms_interval,
        args.ledger_chunk_bytes,
        args.snapshot_tx_interval,
        runners,
    )
