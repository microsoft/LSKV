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

from loguru import logger


# pylint: disable=too-many-arguments
def spawn_node(
    node_index: int,
    workspace: str,
    scheme: str,
    address: str,
    port: int,
    initial_cluster: str,
) -> subprocess.Popen:
    """
    Spawn a new etcd node.
    """
    client_port = port
    peer_port = client_port + 1
    metrics_port = client_port + 2

    name = f"node{node_index}"

    node_dir = os.path.join(workspace, name)
    os.makedirs(node_dir)

    # copy binary files to node dir
    for file in ["bin/etcd"]:
        src = os.path.abspath(file)
        dst = os.path.join(node_dir, os.path.basename(file))
        logger.info("Copying binary file from {} to {}", src, dst)
        shutil.copy(src, dst)

    ca_cert = "ca.pem"
    server_cert = "server.pem"
    server_key = "server-key.pem"
    peer_cert = f"{name}.pem"
    peer_key = f"{name}-key.pem"

    # copy data files to node dir
    for file in [
        os.path.join("certs", n)
        for n in [ca_cert, server_cert, server_key, peer_cert, peer_key]
    ]:
        src = os.path.join(workspace, file)
        dst = os.path.join(node_dir, os.path.basename(file))
        logger.info("Copying data file from {} to {}", src, dst)
        shutil.copy(src, dst)

    cmd = [
        "./etcd",
        "--data-dir",
        "data",
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

    logger.info("running etcd node: {}", " ".join(cmd))

    out = open(os.path.join(node_dir, "out"), "w")
    err = open(os.path.join(node_dir, "err"), "w")

    return subprocess.Popen(cmd, stdout=out, stderr=err, cwd=node_dir)


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

    node_addresses = [
        (n[1].split(":")[0], int(n[1].split(":")[1])) for n in node_addresses_full
    ]
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

    try:
        for i, (ip, port) in enumerate(node_addresses):
            logger.info("spawning node {}: {}", i, (ip, port))
            processes.append(
                spawn_node(
                    i,
                    args.workspace,
                    args.scheme,
                    ip,
                    port,
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

        logger.info("all processes finished")


if __name__ == "__main__":
    main()
