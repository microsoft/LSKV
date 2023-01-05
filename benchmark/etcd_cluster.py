#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Setup and run a local etcd cluster.
"""

import argparse
import os
import os.path
from typing import List, Tuple
import certs
import shutil
import signal
import subprocess
import paramiko

from loguru import logger

class Runner:
    # pylint: disable=too-many-arguments
    def __init__(self,  address: str, port : int, node_index: int, scheme:str, workspace: str, initial_cluster:str):
        self.address = address
        self.port = port
        self.node_index = node_index
        self.scheme = scheme
        self.workspace = workspace
        self.initial_cluster = initial_cluster

    def name(self) -> str:
        return f"node{self.node_index}"


    def node_dir(self)->str:
        node_dir = os.path.join(self.workspace, self.name())
        if not os.path.exists(node_dir):
            os.makedirs(node_dir)
        return node_dir

    def setup_files(self):

        # copy binary files to node dir
        for file in ["bin/etcd"]:
            src = os.path.abspath(file)
            dst = os.path.join(self.node_dir(), os.path.basename(file))
            self.copy_file(src, dst)

        ca_cert = "ca.pem"
        server_cert = "server.pem"
        server_key = "server-key.pem"
        peer_cert = f"{self.name()}.pem"
        peer_key = f"{self.name()}-key.pem"

        # copy data files to node dir
        for file in [
            os.path.join("certs", n)
            for n in [ca_cert, server_cert, server_key, peer_cert, peer_key]
        ]:
            src = os.path.join(self.workspace, file)
            dst = os.path.join(self.node_dir(), os.path.basename(file))
            self.copy_file(src, dst)

    def cmd(self)->str:
        client_port = self.port
        peer_port = client_port + 1
        metrics_port = client_port + 2

        cmd = [
            "./etcd",
            "--data-dir",
            "data",
            "--listen-client-urls",
            f"{self.scheme}://{self.address}:{client_port}",
            "--advertise-client-urls",
            f"{self.scheme}://{self.address}:{client_port}",
            "--listen-peer-urls",
            f"{self.scheme}://{self.address}:{peer_port}",
            "--initial-advertise-peer-urls",
            f"{self.scheme}://{self.address}:{peer_port}",
            "--listen-metrics-urls",
            f"{self.scheme}://{self.address}:{metrics_port}",
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
        cmd_str = f"{cmd_str} > out 2> err"

        return cmd_str


class LocalRunner(Runner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def copy_file(self,src:str, dst:str):
        logger.info("Copying binary file from {} to {}", src, dst)
        shutil.copy(src, dst)

    def start(self):
        self.setup_files()
        cmd = self.cmd()

        logger.info("running etcd node: {}", cmd)

        self.process = subprocess.Popen(cmd, shell=True, cwd=self.node_dir())

    def stop(self):
        self.process.kill()
        self.process.wait()

class RemoteRunner(Runner):
    def __init__(self, *args):
        super().__init__(*args)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(self.address)

        self.client = client

        self.session = self.client.open_sftp()

    def copy_file(self, src:str, dst:str):
        logger.info("Copying file from {} to {}", src, dst)
        self.session.put(src, dst)

    def start(self):
        self.setup_files()
        cmd = self.cmd()

        logger.info("running etcd node: {}", cmd)

        self.process = self.client.exec_command(cmd)


def generate_certs(workspace: str, nodes: List[Tuple[str, int]]):
    """
    Generate certs to be used for the cluster.
    """
    certs_dir = os.path.join(workspace, "certs")
    os.makedirs(certs_dir)
    # cacert
    cfssl = os.path.abspath("bin/cfssl")
    cfssljson = os.path.abspath("bin/cfssljson")
    logger.info("Using cfssl {}", cfssl)
    logger.info("Using cfssljson {}", cfssljson)
    certs.make_ca(certs_dir, cfssl, cfssljson)

    certs.make_certs(certs_dir, cfssl, cfssljson, "server", "server", certs.SERVER_CSR)

    for i, (ip, _port) in enumerate(nodes):
        peer_csr = certs.PEER_CSR
        name = f"node{i}"
        peer_csr["CN"] = name
        if ip not in peer_csr["hosts"]:
            peer_csr["hosts"].append(ip)

        certs.make_certs(certs_dir, cfssl, cfssljson, "peer", name, peer_csr)

    certs.make_certs(certs_dir, cfssl, cfssljson, "client", "client", certs.CLIENT_CSR)


def main():
    """
    Main entry point for spawning the cluster.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", action="extend", nargs="+", type=str, help="The nodes to launch in the form local://ip:port or ssh://ip:port")
    parser.add_argument("--scheme", type=str, default="https", help="scheme to use for connections, either http or https")
    parser.add_argument("--workspace", type=str, default="workspace", help="the workspace dir to use")
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
        for i, (ip, port) in enumerate(node_addresses):
            nodes.append(LocalRunner(address=ip, port=port, node_index=i, scheme=args.scheme, workspace=args.workspace, initial_cluster=initial_cluster))
    elif prefixes[0] == "ssh":
        logger.info("Using ssh")
        for i, (ip, port) in enumerate(node_addresses):
            nodes.append(RemoteRunner(address=ip, port=port, node_index=i, scheme=args.scheme, workspace=args.workspace, initial_cluster=initial_cluster))
    else:
        parser.error("Found unexpected prefix")

    if args.scheme == "https":
        generate_certs(args.workspace, node_addresses)

    try:
        for i, node in enumerate(nodes):
            logger.info("spawning node {}: {}", i, (ip, port))
            node.start()
            logger.info("spawned node {}: {}", i, (ip, port))

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

        logger.info("all nodes finished")


if __name__ == "__main__":
    main()
