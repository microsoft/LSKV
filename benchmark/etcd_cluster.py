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
import tempfile

from loguru import logger


# pylint: disable=too-many-arguments
def spawn_node(
    node_index: int,
    workspace: str,
    scheme: str,
    address: str,
    port: int,
    data_dir: str,
    initial_cluster: str,
) -> subprocess.Popen:
    """
    Spawn a new etcd node.
    """
    client_port = port
    peer_port = client_port + 1
    metrics_port = client_port + 2

    name = f"node{node_index}"
    cmd = [
        "bin/etcd",
        "--data-dir",
        data_dir,
        "--listen-client-urls",
        f"{scheme}://{address}:{client_port}",
        "--advertise-client-urls",
        f"{scheme}://{address}:{client_port}",
        "--listen-peer-urls",
        f"{scheme}://{address}:{peer_port}",
        "--initial-advertise-peer-urls",
        f"{scheme}://{address}:{peer_port}",
        "--listen-metrics-urls",
        f"{scheme}://{address}:{metrics_port}",
        "--initial-cluster",
        initial_cluster,
        "--initial-cluster-state",
        "new",
        "--name",
        name,
    ]

    if scheme == "https":
        certs_dir = os.path.join(workspace, "certs")
        cmd += [
            "--trusted-ca-file",
            os.path.join(certs_dir, "ca.pem"),
            "--cert-file",
            os.path.join(certs_dir, "server.pem"),
            "--key-file",
            os.path.join(certs_dir, f"server-key.pem"),
            "--client-cert-auth",
            "--peer-trusted-ca-file",
            os.path.join(certs_dir, "ca.pem"),
            "--peer-cert-file",
            os.path.join(certs_dir, f"{name}.pem"),
            "--peer-key-file",
            os.path.join(certs_dir, f"{name}-key.pem"),
            "--peer-client-cert-auth",
        ]

    logger.info("running etcd node: {}", " ".join(cmd))

    return subprocess.Popen(cmd)


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
    parser.add_argument("--node", action="extend", nargs="+", type=str)
    parser.add_argument("--scheme", type=str, default="https")
    parser.add_argument("--workspace", type=str, default="workspace")
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

    if prefixes[0] == "local":
        logger.info("Using local")
    elif prefixes[0] == "ssh":
        logger.info("Using ssh")
    else:
        parser.error("Found unexpected prefix")

    node_addresses = [(n[1].split(":")[0], int(n[1].split(":")[1])) for n in node_addresses_full]
    logger.info("Made addresses {}", node_addresses)

    if args.scheme == "https":
        generate_certs(args.workspace, node_addresses)

    initial_cluster = ",".join(
        [
            f"node{i}={args.scheme}://{ip}:{port + 1}"
            for i, (ip, port) in enumerate(node_addresses)
        ]
    )
    logger.info("Built initial cluster {}", initial_cluster)

    processes = []
    data_dirs = []

    try:
        for i, (ip, port) in enumerate(node_addresses):
            logger.info("spawning node {}: {}", i, (ip, port))
            data_dir = tempfile.mkdtemp()
            data_dirs.append(data_dir)
            processes.append(
                spawn_node(
                    i,
                    args.workspace,
                    args.scheme,
                    ip,
                    port,
                    data_dir,
                    initial_cluster,
                )
            )
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
        for i, process in enumerate(processes):
            logger.info("killing process {}", i)
            process.kill()
            logger.info("waiting for process {}", i)
            process.wait()

        for i, data_dir in enumerate(data_dirs):
            logger.info("removing data dir {}: {}", i, data_dir)
            shutil.rmtree(data_dir)

        logger.info("all processes finished")


if __name__ == "__main__":
    main()
