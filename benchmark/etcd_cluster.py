#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Setup and run a local etcd cluster.
"""

import argparse
import os
import os.path
import shutil
import signal
import subprocess
from typing import List, Tuple

import paramiko
from loguru import logger

import certs


class Runner:
    """
    Class to manage running a node as part of a cluster.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        address: str,
        port: int,
        node_index: int,
        scheme: str,
        workspace: str,
        initial_cluster: str,
        docker_image: str,
        tmpfs: bool,
        pull: bool,
    ):
        self.address = address
        self.port = port
        self.node_index = node_index
        self.scheme = scheme
        self.workspace = workspace
        self.initial_cluster = initial_cluster
        self.docker_image = docker_image
        self.tmpfs = tmpfs
        self.pull = pull

    def name(self) -> str:
        """
        Return the name for a node.
        """
        return f"node{self.node_index}"

    def node_dir(self) -> str:
        """
        Working directory for the node.
        """
        return os.path.join(self.workspace, self.name())

    def copy_file(self, _src: str, _dst: str):
        """
        Copy a file.
        """
        raise NotImplementedError("copy_file not implemented.")

    def fetch_file(self, _src: str, _dst: str):
        """
        Copy a file.
        """
        raise NotImplementedError("fetch_file not implemented.")

    def run(self, cmd: str):
        """
        Run a command.
        """
        raise NotImplementedError("run not implemented.")

    def setup_common(self):
        """
        Set up common files.
        """

        common_dir = os.path.join(self.workspace, "common")
        subprocess.run(["mkdir", "-p", common_dir], check=True)

    def setup_files(self):
        """
        Copy files needed to run to the working directory.
        """
        if self.pull:
            self.run(f"docker pull {self.docker_image}")

        ca_cert = "ca.pem"
        server_cert = "server.pem"
        server_key = "server-key.pem"
        peer_cert = f"{self.name()}.pem"
        peer_key = f"{self.name()}-key.pem"

        # copy data files to node dir
        for file in [
            os.path.join("common", n)
            for n in [ca_cert, server_cert, server_key, peer_cert, peer_key]
        ]:
            src = os.path.join(self.workspace, file)
            dst = os.path.join(self.node_dir(), os.path.basename(file))
            self.copy_file(src, dst)

    def cmd(self) -> str:
        """
        Command to run to start this node.
        """
        client_port = self.port
        peer_port = client_port + 1
        metrics_port = client_port + 2

        cmd = [
            "etcd",
            "--data-dir",
            "/data",
            "--listen-client-urls",
            f"{self.scheme}://{self.address}:{client_port}",
            "--advertise-client-urls",
            f"{self.scheme}://{self.address}:{client_port}",
            "--listen-peer-urls",
            f"{self.scheme}://{self.address}:{peer_port}",
            "--initial-advertise-peer-urls",
            f"{self.scheme}://{self.address}:{peer_port}",
            "--listen-metrics-urls",
            f"http://{self.address}:{metrics_port}",
            "--initial-cluster",
            self.initial_cluster,
            "--initial-cluster-state",
            "new",
            "--name",
            self.name(),
        ]

        ca_cert = "ca.pem"
        server_cert = "server.pem"
        server_key = "server-key.pem"
        peer_cert = f"{self.name()}.pem"
        peer_key = f"{self.name()}-key.pem"

        if self.scheme == "https":
            cmd += [
                "--trusted-ca-file",
                ca_cert,
                "--cert-file",
                server_cert,
                "--key-file",
                server_key,
                "--client-cert-auth",
                "--peer-trusted-ca-file",
                ca_cert,
                "--peer-cert-file",
                peer_cert,
                "--peer-key-file",
                peer_key,
                "--peer-client-cert-auth",
            ]

        cmd_str = " ".join(cmd)
        tmpfs_mount = ""
        if self.tmpfs:
            tmpfs_mount = "--mount type=tmpfs,destination=/data"
        cmd_str = f"cd {self.node_dir()} && docker run --rm --name {self.name()} -w /workspace --network host {tmpfs_mount} -v {self.node_dir()}:/workspace:ro {self.docker_image} {cmd_str} >out 2>err"

        return cmd_str


class LocalRunner(Runner):
    """
    Run a local node as a unix process.
    """

    def copy_file(self, src: str, dst: str):
        """
        Copy a file.
        """
        logger.info("[{}] Copying file from {} to {}", self.address, src, dst)
        shutil.copy(src, dst)

    def fetch_file(self, src: str, dst: str):
        """
        Fetch a remote file.
        """
        logger.info("[{}] Fetching file from {} to {}", self.address, src, dst)

    def run(self, cmd: str):
        logger.info("[{}] Running command '{}'", self.address, cmd)
        subprocess.run(cmd, check=True, shell=True)

    def start(self):
        """
        Start a node, copying required files first.
        """
        shutil.rmtree(self.node_dir(), ignore_errors=True)
        os.makedirs(self.node_dir())
        self.setup_files()
        logger.info("[{}] Removing containers {}", self.address, self.name())
        subprocess.run(["docker", "rm", "-f", self.name()], check=True)
        cmd = self.cmd()

        logger.info("running etcd node: {}", cmd)

        # pylint: disable=consider-using-with
        subprocess.Popen(cmd, shell=True)

    def stop(self):
        """
        Stop a node.
        """
        subprocess.run(["docker", "rm", "-f", self.name()], check=True)


class RemoteRunner(Runner):
    """
    Run a node on a remote machine.
    """

    def __init__(self, username: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if not username:
            username = os.getlogin()
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

    def fetch_file(self, src: str, dst: str):
        """
        Fetch a remote file.
        """
        logger.info("[{}] Fetching file from {} to {}", self.address, src, dst)
        self.session.get(src, dst)

    def run(self, cmd: str):
        logger.info("[{}] Running command '{}'", self.address, cmd)
        _, stdout, _ = self.client.exec_command(cmd)
        stdout.channel.recv_exit_status()

    def start(self):
        """
        Start a node.
        """
        shutil.rmtree(self.node_dir(), ignore_errors=True)
        _, stdout, _ = self.client.exec_command(f"rm -rf {self.node_dir()}")
        stdout.channel.recv_exit_status()
        os.makedirs(self.node_dir())
        _, stdout, _ = self.client.exec_command(f"mkdir -p {self.node_dir()}")
        stdout.channel.recv_exit_status()

        self.setup_files()
        cmd = self.cmd()

        logger.info("running etcd node: {}", cmd)

        self.client.exec_command(cmd)

    def stop(self):
        """
        Stop a node.
        """
        _, stdout, _ = self.client.exec_command(f"docker rm -f {self.name()}")
        stdout.channel.recv_exit_status()
        out_file = os.path.join(self.node_dir(), "out")
        self.session.get(out_file, out_file)
        err_file = os.path.join(self.node_dir(), "err")
        self.session.get(err_file, err_file)


def generate_certs(workspace: str, nodes: List[Tuple[str, int]]):
    """
    Generate certs to be used for the cluster.
    """
    common_dir = os.path.join(workspace, "common")
    os.makedirs(common_dir)
    # cacert
    cfssl = os.path.abspath("bin/cfssl")
    cfssljson = os.path.abspath("bin/cfssljson")
    logger.info("Using cfssl {}", cfssl)
    logger.info("Using cfssljson {}", cfssljson)
    certs.make_ca(common_dir, cfssl, cfssljson)
    # for similarity to CCF
    shutil.copyfile(
        os.path.join(common_dir, "ca.pem"), os.path.join(common_dir, "service_cert.pem")
    )

    ip_addresses = {a for (a, _) in nodes}.union({"127.0.0.1"})
    server_csr = certs.SERVER_CSR
    server_csr["hosts"] = list(ip_addresses)
    certs.make_certs(common_dir, cfssl, cfssljson, "server", "server", server_csr)

    for i, (ip_addr, _port) in enumerate(nodes):
        peer_csr = certs.PEER_CSR
        name = f"node{i}"
        peer_csr["CN"] = name
        if ip_addr not in peer_csr["hosts"]:
            hosts = peer_csr["hosts"]
            assert isinstance(hosts, list)
            hosts.append(ip_addr)

        certs.make_certs(common_dir, cfssl, cfssljson, "peer", name, peer_csr)

    certs.make_certs(common_dir, cfssl, cfssljson, "client", "client", certs.CLIENT_CSR)
    # for similarity to CCF
    shutil.copyfile(
        os.path.join(common_dir, "client.pem"),
        os.path.join(common_dir, "user0_cert.pem"),
    )
    shutil.copyfile(
        os.path.join(common_dir, "client-key.pem"),
        os.path.join(common_dir, "user0_privk.pem"),
    )


# pylint: disable=too-many-branches
def main():
    """
    Main entry point for spawning the cluster.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--node",
        action="extend",
        nargs="+",
        type=str,
        help="The nodes to launch in the form local://ip:port or ssh://ip:port",
    )
    parser.add_argument(
        "--scheme",
        type=str,
        default="https",
        help="scheme to use for connections, either http or https",
    )
    parser.add_argument(
        "--workspace", type=str, default="workspace", help="the workspace dir to use"
    )
    parser.add_argument(
        "--tmpfs", action="store_true", help="Whether to store data on tmpfs"
    )
    parser.add_argument("--pull", action="store_true", help="Whether to pull the image")
    parser.add_argument(
        "--docker-image",
        type=str,
        default="gcr.io/etcd-development/etcd:v3.5.4",
        help="Which docker image to use",
    )
    parser.add_argument(
        "--ssh-user",
        type=str,
        default="",
    )
    args = parser.parse_args()

    if not args.node:
        parser.error("must have at least one node to run")

    args.workspace = os.path.abspath(args.workspace)

    logger.info("using config {}", args)

    if os.path.exists(args.workspace):
        logger.info("Removing existing workspace dir: {}", args.workspace)
        shutil.rmtree(args.workspace)
    os.makedirs(args.workspace)

    node_addresses_full = [n.split("://") for n in args.node]
    prefixes = list({n[0] for n in node_addresses_full})
    if len(prefixes) != 1:
        parser.error("nodes should all have the same prefix")

    node_addresses = [
        (n[1].split(":")[0], int(n[1].split(":")[1])) for n in node_addresses_full
    ]
    logger.info("Made addresses {}", node_addresses)

    initial_cluster = ",".join(
        [
            f"node{i}={args.scheme}://{ip}:{port + 1}"
            for i, (ip, port) in enumerate(node_addresses)
        ]
    )
    logger.info("Built initial cluster {}", initial_cluster)

    nodes = []
    if prefixes[0] == "local":
        logger.info("Using local")
        for i, (ip_addr, port) in enumerate(node_addresses):
            nodes.append(
                LocalRunner(
                    address=ip_addr,
                    port=port,
                    node_index=i,
                    scheme=args.scheme,
                    workspace=args.workspace,
                    initial_cluster=initial_cluster,
                    docker_image=args.docker_image,
                    tmpfs=args.tmpfs,
                    pull=args.pull,
                )
            )
    elif prefixes[0] == "ssh":
        logger.info("Using ssh")
        for i, (ip_addr, port) in enumerate(node_addresses):
            nodes.append(
                RemoteRunner(
                    username=args.ssh_user,
                    address=ip_addr,
                    port=port,
                    node_index=i,
                    scheme=args.scheme,
                    workspace=args.workspace,
                    initial_cluster=initial_cluster,
                    docker_image=args.docker_image,
                    tmpfs=args.tmpfs,
                    pull=args.pull,
                )
            )
    else:
        parser.error("Found unexpected prefix")

    if args.scheme == "https":
        generate_certs(args.workspace, node_addresses)

    try:
        nodes[0].setup_common()
        for i, node in enumerate(nodes):
            logger.info("spawning node {}: {}", i, node.address, node.port)
            node.start()
            logger.info("spawned node {}: {}", i, node.address, node.port)

        # wait for a signal and print it out
        signals = {signal.SIGINT, signal.SIGTERM}
        # have to set the thread mask: https://bugs.python.org/issue38284
        signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        logger.info("waiting for a signal")
        sig = signal.sigwait(signals)
        logger.info("received a signal: {}", signal.Signals(sig).name)
    # pylint: disable=broad-except
    except Exception as exception:
        logger.exception("exception while spawning nodes: {}", exception)
    finally:
        for i, node in enumerate(nodes):
            logger.info("stopping node {}", i)
            node.stop()
            logger.info("Fetching node logs for {}", i)

            out_file = os.path.join(node.node_dir(), "out")
            err_file = os.path.join(node.node_dir(), "err")
            node.fetch_file(out_file, out_file)
            node.fetch_file(err_file, err_file)

        logger.info("all nodes finished")


if __name__ == "__main__":
    main()
