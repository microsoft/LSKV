#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import signal
import tempfile
import argparse
import shutil
from loguru import logger
import subprocess

BASE_PORT = 8000


def spawn_node(
    address: str,
    port: int,
    data_dir:str,
    initial_cluster: str,
    cacert: str,
    cert: str,
    key: str,
    peer_cacert: str,
    peer_cert: str,
    peer_key: str,
) -> subprocess.Popen:
    client_port = BASE_PORT + 3 * port
    peer_port = client_port + 1
    metrics_port = client_port + 2


    cmd = [
        "bin/etcd",
        "--data-dir",
        data_dir,
        "--listen-client-urls",
        f"{address}:{client_port}",
        "--advertise-client-urls",
        f"{address}:{client_port}",
        "--listen-peer-urls",
        f"{address}:{peer_port}",
        "--initial-advertise-peer-urls",
        f"{address}:{peer_port}",
        "--initial-cluster",
        initial_cluster,
        "--initial-cluster-state",
        "new",
        "--name",
        f"node{port}",
        "--listen-metrics-urls",
        f"{address}:{metrics_port}",
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, default=1)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--address", type=str, default="https://127.0.0.1")
    parser.add_argument("--cacert", type=str, default="certs/ca.pem")
    parser.add_argument("--cert", type=str, default="certs/server.pem")
    parser.add_argument("--key", type=str, default="certs/server-key.pem")
    parser.add_argument("--peer-cacert", type=str, default="certs/ca.pem")
    parser.add_argument("--peer-cert-base", type=str, default="certs/node")
    args = parser.parse_args()

    logger.info("using config {}", args)

    initial_cluster = ",".join(
        [f"node{i}={args.address}:{BASE_PORT + 3 * i + 1}" for i in range(args.nodes)]
    )

    processes = []
    data_dirs = []

    try:
        for i in range(args.nodes):
            logger.info("spawning node {}", i)
            data_dir = tempfile.mkdtemp()
            data_dirs.append(data_dir)
            peer_cert = f"{args.peer_cert_base}{i}.pem"
            peer_key = f"{args.peer_cert_base}{i}-key.pem"
            processes.append(
                spawn_node(
                    args.address,
                    i,
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
            logger.info("spawned node {}", i)

        logger.info("waiting for a signal")
        sig = signal.sigwait([signal.SIGINT, signal.SIGTERM])
        logger.info("received a signal: {}", signal.Signals(sig).name)
    except Exception as e:
        logger.exception("exception while spawning nodes: {}", e)
    finally:
        for i, p in enumerate(processes):
            logger.info("killing process {}", i)
            p.kill()
            logger.info("waiting for process {}", i)
            p.wait()

        for i, d in enumerate(data_dirs):
            logger.info("removing data dir {}: {}", i, d)
            shutil.rmtree(d)

        logger.info("all processes finished")
