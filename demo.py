#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import argparse
import base64
import json
import subprocess
from pprint import pprint
from typing import Any, Dict, List, Tuple

from loguru import logger


def run(
    cmd: List[str], json_resp=True, silent=False, wait=True, **kwargs
) -> subprocess.CompletedProcess:
    """
    Run a command.
    """
    cmd_str = subprocess.list2cmdline(cmd)
    if wait:
        input(f"Run: {cmd_str}")
    else:
        print(f"Run: {cmd_str}")

    # pylint: disable=subprocess-run-check
    proc = subprocess.run(cmd, capture_output=True, **kwargs)
    if proc.returncode != 0:
        logger.warning("Command failed, returned {}", proc.returncode)
    if not silent and proc.stdout:
        data = proc.stdout
        if json_resp:
            data = json.loads(data)
            pprint(data)
        else:
            print(data)
    if not silent and proc.stderr:
        logger.debug("stderr: {}", proc.stderr)
    proc.check_returncode()
    return proc


class Curl:
    def __init__(self, port: int, common_dir: str):
        self.address = f"https://127.0.0.1:{port}"
        self.common_dir = common_dir

    def base_cmd(self) -> List[str]:
        return ["curl", "-s", "--cacert", f"{self.common_dir}/service_cert.pem"]

    def get(self, key: str, rev: int = 0):
        data: Dict[str, Any] = {"key": key}
        if rev:
            data["revision"] = rev
        run(
            self.base_cmd()
            + [
                "-X",
                "POST",
                f"{self.address}/v3/kv/range",
                "-d",
                json.dumps(data),
                "-H",
                "content-type: application/json",
            ]
        )

    def put(self, key: str, value: str) -> Tuple[int, int]:
        data = {
            "key": key,
            "value": value,
        }
        res = run(
            self.base_cmd()
            + [
                "-X",
                "POST",
                f"{self.address}/v3/kv/put",
                "-d",
                json.dumps(data),
                "-H",
                "content-type: application/json",
            ]
        )

        header = json.loads(res.stdout.decode("utf-8"))["header"]
        rev = header["revision"]
        if "raftTerm" in header:
            term = header["raftTerm"]
        elif "raft_term" in header:
            term = header["raft_term"]

        return (term, rev)

    def delete(self, key: str):
        data = {
            "key": key,
        }
        run(
            self.base_cmd()
            + [
                "-X",
                "POST",
                f"{self.address}/v3/kv/delete_range",
                "-d",
                json.dumps(data),
                "-H",
                "content-type: application/json",
            ]
        )

    def tx_status(self, term: int, rev: int, wait=True):
        txid = f"{term}.{rev}"
        run(
            self.base_cmd()
            + ["-X", "GET", f"{self.address}/app/tx?transaction_id={txid}"],wait=wait
        )

    def get_receipt(self, term: int, rev: int):
        data = {
            "raft_term": term,
            "revision": rev,
        }
        # trigger it
        run(
            self.base_cmd()
            + [
                "-X",
                "POST",
                f"{self.address}/v3/receipt/get_receipt",
                "-d",
                json.dumps(data),
                "-H",
                "content-type: application/json",
            ],
            json_resp=False,
        )
        # actually get the receipt
        run(
            self.base_cmd()
            + [
                "-X",
                "POST",
                f"{self.address}/v3/receipt/get_receipt",
                "-d",
                json.dumps(data),
                "-H",
                "content-type: application/json",
            ]
        )

    def list_endpoints(self):
        res = run(
            self.base_cmd() + ["-X", "GET", f"{self.address}/app/api"], silent=True
        )
        data = res.stdout.decode("utf-8")
        pprint(list(json.loads(data)["paths"].keys()))


class Etcdctl:
    def __init__(self, port: int, common_dir: str):
        self.address = f"https://127.0.0.1:{port}"
        self.common_dir = common_dir
        self.curl = Curl(port, common_dir)

    def base_cmd(self) -> List[str]:
        return [
            "bin/etcdctl",
            "--endpoints",
            self.address,
            "--cacert",
            f"{self.common_dir}/service_cert.pem",
            "-w",
            "json",
        ]

    def get(self, key: str, rev: int = 0):
        cmd = self.base_cmd() + ["get", key]
        if rev:
            cmd += ["--rev", str(rev)]
        run(cmd)

    def put(self, key: str, value: str) -> Tuple[int, int]:
        cmd = self.base_cmd() + ["put", key, value]
        res = run(cmd)

        header = json.loads(res.stdout.decode("utf-8"))["header"]
        rev = header["revision"]
        if "raftTerm" in header:
            term = header["raftTerm"]
        elif "raft_term" in header:
            term = header["raft_term"]

        return (term, rev)

    def delete(self, key: str):
        cmd = self.base_cmd() + ["del", key]
        run(cmd)

    def tx_status(self, term: int, rev: int, wait=True):
        txid = f"{term}.{rev}"
        run(
            self.curl.base_cmd()
            + ["-X", "GET", f"{self.address}/app/tx?transaction_id={txid}"],wait=wait
        )

    def get_receipt(self, term: int, rev: int):
        data = {
            "raft_term": term,
            "revision": rev,
        }
        # trigger it
        run(
            self.curl.base_cmd()
            + [
                "-X",
                "POST",
                f"{self.address}/v3/receipt/get_receipt",
                "-d",
                json.dumps(data),
                "-H",
                "content-type: application/json",
            ],
            json_resp=False,
        )
        # actually get the receipt
        run(
            self.curl.base_cmd()
            + [
                "-X",
                "POST",
                f"{self.address}/v3/receipt/get_receipt",
                "-d",
                json.dumps(data),
                "-H",
                "content-type: application/json",
            ]
        )

    def list_endpoints(self):
        res = run(
            self.curl.base_cmd() + ["-X", "GET", f"{self.address}/app/api"], silent=True
        )
        data = res.stdout.decode("utf-8")
        pprint(list(json.loads(data)["paths"].keys()))


def to_b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")


def main(port: int, common_dir: str, client_type: str):
    user_key = "hello"
    user_value = "ccf"

    if client_type == "curl":
        client = Curl(port, common_dir)
        key = to_b64(user_key)
        value = to_b64(user_value)
    elif client_type == "etcd":
        client = Etcdctl(port, common_dir)
        key = user_key
        value = user_value
    else:
        raise ValueError(f"incorrect client type: {client_type}")

    client.list_endpoints()

    # get missing key
    print()
    print("Check that the key doesn't exist")
    client.get(key)

    # write a value
    print()
    print("Add a value for the key")
    put_term, put_rev = client.put(key, value)
    client.tx_status(put_term, put_rev, wait=False)

    print()
    print("Check the status of the commit")
    client.tx_status(put_term, put_rev)

    # read the value
    print()
    print("And get the value we just wrote")
    client.get(key)

    # delete the value
    print()
    print("But we don't need it any more so delete it")
    client.delete(key)

    # read the value
    print()
    print("And check we can't read it")
    client.get(key)

    # get the value from the past
    print()
    print("But we can time-travel")
    client.get(key, rev=put_rev)

    # now get a receipt for the write we did
    print()
    print("Now what if we want to verify that what we wrote is in the ledger?")
    client.get_receipt(put_term, put_rev)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default="8000")
    parser.add_argument("--common", type=str, default="workspace/sandbox_common")
    parser.add_argument("--client", type=str, default="etcd")
    args = parser.parse_args()
    main(args.port, args.common, args.client)
