#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Setup and run a local etcd cluster.
"""

import argparse
import shutil
import signal
import subprocess
import tempfile

from loguru import logger


# pylint: disable=too-many-arguments
def spawn_node(
    node_index: int,
    scheme: str,
    address: str,
    port: int,
    data_dir: str,
    initial_cluster: str,
    cacert: str,
    cert: str,
    key: str,
    peer_cacert: str,
    peer_cert: str,
    peer_key: str,
) -> subprocess.Popen:
    """
    Spawn a new etcd node.
    """
    client_port = port
    peer_port = client_port + 1
    metrics_port = client_port + 2

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
        f"node{node_index}",
    ]
    if scheme == "https":
        cmd += [
            "--trusted-ca-file",
            cacert,
            "--cert-file",
            cert,
            "--key-file",
            key,
            "--client-cert-auth",
            "--peer-trusted-ca-file",
            peer_cacert,
            "--peer-cert-file",
            peer_cert,
            "--peer-key-file",
            peer_key,
            "--peer-client-cert-auth",
        ]

    logger.info("running etcd node: {}", " ".join(cmd))

    return subprocess.Popen(cmd)


def main():
    """
    Main entry point for spawning the cluster.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", action="extend", nargs="+", type=str)
    parser.add_argument("--scheme", type=str, default="https")
    parser.add_argument("--cacert", type=str, default="certs/ca.pem")
    parser.add_argument("--cert", type=str, default="certs/server.pem")
    parser.add_argument("--key", type=str, default="certs/server-key.pem")
    parser.add_argument("--peer-cacert", type=str, default="certs/ca.pem")
    parser.add_argument("--peer-cert-base", type=str, default="certs/node")
    args = parser.parse_args()

    if not args.node:
        parser.error("must have at least one node to run")

    logger.info("using config {}", args)

    node_addresses = [n.split("://")[1] for n in args.node]
    node_addresses = [(n.split(":")[0], int(n.split(":")[1]) )for n in node_addresses]
    logger.info("Made addresses {}", node_addresses)

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
            peer_cert = f"{args.peer_cert_base}{i}.pem"
            peer_key = f"{args.peer_cert_base}{i}-key.pem"
            processes.append(
                spawn_node(
                    i,
                    args.scheme,
                    ip,
                    port,
                    data_dir,
                    initial_cluster,
                    args.cacert,
                    args.cert,
                    args.key,
                    args.peer_cacert,
                    peer_cert,
                    peer_key,
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
