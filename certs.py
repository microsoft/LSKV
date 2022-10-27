#!/usr/bin/env python3

import subprocess
import sys
import argparse
from loguru import logger
import json
from typing import Dict
import shutil
import os

CA_CONFIG = {
    "signing": {
        "default": {"expiry": "8760h"},
        "profiles": {
            "server": {
                "expiry": "8760h",
                "usages": ["signing", "key encipherment", "server auth", "client auth"],
            },
            "client": {
                "expiry": "8760h",
                "usages": ["signing", "key encipherment", "client auth"],
            },
            "peer": {
                "expiry": "8760h",
                "usages": ["signing", "key encipherment", "server auth", "client auth"],
            },
        },
    }
}

CA_CSR = {
    "CN": "auto-ca",
    "hosts": ["127.0.0.1"],
    "key": {"algo": "ecdsa", "size": 384},
    "names": [{"C": "UK", "L": "London", "ST": "London"}],
}

SERVER_CSR = {
    "CN": "etcd",
    "hosts": [ "127.0.0.1"],
    "key": {"algo": "ecdsa", "size": 384},
    "names": [{"C": "UK", "L": "London", "ST": "London"}],
}

PEER_CSR = {
    "CN": "node0",
    "hosts": [ "127.0.0.1"],
    "key": {"algo": "ecdsa", "size": 384},
    "names": [{"C": "UK", "L": "London", "ST": "London"}],
}

CLIENT_CSR = {
    "CN": "client",
    "hosts": [""],
    "key": {"algo": "ecdsa", "size": 384},
    "names": [{"C": "UK", "L": "London", "ST": "London"}],
}


def make_ca(certs: str, cfssl: str, cfssljson: str):
    """
    Make a CA certificate with cfssl.
    """
    logger.info("Making CA certificate")
    with open(os.path.join(certs, "ca-config.json"), "w", encoding="utf-8") as f:
        logger.info("Writing CA config to {}", f.name)
        f.write(json.dumps(CA_CONFIG))
    with open(os.path.join(certs, "ca-csr.json"), "w", encoding="utf-8") as f:
        logger.info("Writing CA csr to {}", f.name)
        f.write(json.dumps(CA_CSR))
    logger.info("Running cfssl gencert")
    subprocess.run(
        f"{cfssl} gencert -initca ca-csr.json | {cfssljson} -bare ca -",
        input=json.dumps(CA_CSR).encode("utf-8"),
        cwd=certs,
        shell=True,
        check=True,
    )


def make_certs(
    certs: str,
    cfssl: str,
    cfssljson: str,
    profile: str,
    name: str,
    data: Dict[str, any],
):
    """
    Make certs with cfssl
    """
    logger.info("Making certificates for {}", name)
    with open(os.path.join(certs, f"{name}.json"), "w", encoding="utf-8") as f:
        logger.info("Writing csr to {}", f.name)
        f.write(json.dumps(data))
    logger.info("Running cfssl gencert")
    subprocess.run(
        f"{cfssl} gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile={profile} {name}.json | {cfssljson} -bare {name} -",
        input=json.dumps(CA_CSR).encode("utf-8"),
        cwd=certs,
        shell=True,
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--nodes", type=int, default=3, help="Number of nodes to generate certs for"
    )
    parser.add_argument(
        "--certs-dir", type=str, default="certs", help="Directory to store certs"
    )
    parser.add_argument(
        "--cfssl", type=str, default="bin/cfssl", help="Path to cfssl binary"
    )
    parser.add_argument(
        "--cfssljson",
        type=str,
        default="bin/cfssljson",
        help="Path to cfssljson binary",
    )
    args = parser.parse_args()

    logger.info("Generating certificates with arguments: {}", args)

    certs_dir = args.certs_dir
    logger.info("Removing certs dir: {}", certs_dir)
    shutil.rmtree(certs_dir, ignore_errors=True)
    logger.info("Creating certs dir: {}", certs_dir)
    os.makedirs(certs_dir)

    cfssl = os.path.abspath(args.cfssl)
    if os.path.exists(cfssl):
        logger.info("Found cfssl: {}", cfssl)
    else:
        logger.info("Failed to find cfssl: {}", cfssl)
        sys.exit(1)

    cfssljson = os.path.abspath(args.cfssljson)
    if os.path.exists(cfssljson):
        logger.info("Found cfssljson: {}", cfssljson)
    else:
        logger.info("Failed to find cfssljson: {}", cfssljson)
        sys.exit(1)

    make_ca(certs_dir, cfssl, cfssljson)
    make_certs(certs_dir, cfssl, cfssljson, "server", "server", SERVER_CSR)
    num_nodes = args.nodes
    for i in range(num_nodes):
        peer_csr = PEER_CSR
        name = f"node{i}"
        peer_csr["CN"] = name
        peer_csr["hosts"].append(name)
        make_certs(certs_dir, cfssl, cfssljson, "peer", name, peer_csr)
    make_certs(certs_dir, cfssl, cfssljson, "client", "client", CLIENT_CSR)


if __name__ == "__main__":
    main()
