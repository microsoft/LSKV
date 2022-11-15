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


def to_nice_json(j: Any) -> Any:
    """
    Convert etcd json output base64 strings to nice strings.
    """
    if isinstance(j, dict):
        for k, v in j.items():
            j[k] = to_nice_json(v)
    if isinstance(j, list):
        for i, v in enumerate(j):
            j[i] = to_nice_json(v)
    if isinstance(j, str):
        try:
            return from_b64(j)
        except Exception:
            return j
    return j


def load_pretty_json(j: str) -> Any:
    data = json.loads(j)
    return to_nice_json(data)


def run(
    cmd: List[str],
    load_json=json.loads,
    json_resp=True,
    silent=False,
    cmd_silent=False,
    wait=True,
    **kwargs,
) -> subprocess.CompletedProcess:
    """
    Run a command.
    """
    cmd_str = subprocess.list2cmdline(cmd)
    if wait:
        input(f"Run: {cmd_str}")
    elif not cmd_silent:
        print(f"Run: {cmd_str}")

    # pylint: disable=subprocess-run-check
    proc = subprocess.run(cmd, capture_output=True, **kwargs)
    if proc.returncode != 0:
        logger.warning("Command failed, returned {}", proc.returncode)
    if not silent and proc.stdout:
        data = proc.stdout
        if json_resp:
            data = load_json(data)
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

    def get(self, key: str, end: str = "", rev: int = 0):
        data: Dict[str, Any] = {"key": key}
        if rev:
            data["revision"] = rev
        if end:
            data["range_end"] = end
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
            ],
            load_json=load_pretty_json,
        )

    def put(self, key: str, value: str, **kwargs) -> Tuple[int, int]:
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
            ],
            load_json=load_pretty_json,
            **kwargs,
        )

        header = json.loads(res.stdout.decode("utf-8"))["header"]
        rev = header["revision"]
        if "raftTerm" in header:
            term = header["raftTerm"]
        elif "raft_term" in header:
            term = header["raft_term"]
        else:
            raise ValueError(f"missing raft term in header: {header}")

        return (term, rev)

    def delete(self, key: str, end: str = ""):
        data = {
            "key": key,
        }
        if end:
            data["range_end"] = end
        res = run(
            self.base_cmd()
            + [
                "-X",
                "POST",
                f"{self.address}/v3/kv/delete_range",
                "-d",
                json.dumps(data),
                "-H",
                "content-type: application/json",
            ],
            load_json=load_pretty_json,
        )
        header = json.loads(res.stdout.decode("utf-8"))["header"]
        rev = header["revision"]
        if "raftTerm" in header:
            term = header["raftTerm"]
        elif "raft_term" in header:
            term = header["raft_term"]
        else:
            raise ValueError(f"missing raft term in header: {header}")

        return (term, rev)

    def tx_status(self, term: int, rev: int, **kwargs):
        txid = f"{term}.{rev}"
        run(
            self.base_cmd()
            + ["-X", "GET", f"{self.address}/app/tx?transaction_id={txid}"],
            **kwargs,
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
            self.base_cmd() + ["-X", "GET", f"{self.address}/app/api"],
            silent=True,
            load_json=load_pretty_json,
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

    def get(self, key: str, end: str = "", rev: int = 0):
        cmd = self.base_cmd() + ["get", key]
        if end:
            cmd += [end]
        if rev:
            cmd += ["--rev", str(rev)]
        run(
            cmd,
            load_json=load_pretty_json,
        )

    def put(self, key: str, value: str, **kwargs) -> Tuple[int, int]:
        cmd = self.base_cmd() + ["put", key, value]
        res = run(cmd, load_json=load_pretty_json, **kwargs)

        header = json.loads(res.stdout.decode("utf-8"))["header"]
        rev = header["revision"]
        if "raftTerm" in header:
            term = header["raftTerm"]
        elif "raft_term" in header:
            term = header["raft_term"]
        else:
            raise ValueError(f"missing raft term in header: {header}")

        return (term, rev)

    def delete(self, key: str, end: str = ""):
        cmd = self.base_cmd() + ["del", key]
        if end:
            cmd += [end]
        res = run(
            cmd,
            load_json=load_pretty_json,
        )
        header = json.loads(res.stdout.decode("utf-8"))["header"]
        rev = header["revision"]
        if "raftTerm" in header:
            term = header["raftTerm"]
        elif "raft_term" in header:
            term = header["raft_term"]
        else:
            raise ValueError(f"missing raft term in header: {header}")

        return (term, rev)

    def tx_status(self, term: int, rev: int, **kwargs):
        txid = f"{term}.{rev}"
        run(
            self.curl.base_cmd()
            + ["-X", "GET", f"{self.address}/app/tx?transaction_id={txid}"],
            **kwargs,
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


def from_b64(s: str) -> str:
    return base64.b64decode(s.encode("utf-8")).decode("utf-8")


def make_key(i: int, s: str = "hello") -> str:
    return f"{s}{i}"


def make_value(i: int) -> str:
    return f"ccf{i}"


def prefill(client, i: int):
    for i in range(i):
        client.put(
            make_key(i, s="_prefill"),
            make_value(i),
            wait=False,
            silent=True,
            cmd_silent=True,
        )


def main(port: int, common_dir: str, client_type: str):
    user_key = make_key(0)
    user_value = make_value(0)

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

    prefill_size = 100
    print(f"Prefilling {prefill_size} keys")
    prefill(client, prefill_size)

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

    print()
    input("Add some more values")
    for i in range(10):
        keyi = make_key(i)
        vali = make_value(i)
        put_term, put_rev = client.put(keyi, vali, wait=False, silent=True)

    # read the value
    print()
    print("And get the value we just wrote")
    client.get(make_key(1), make_key(5))

    # read all the values
    print()
    print("And get the value we just wrote")
    client.get("a", "z")

    # delete the value
    print()
    print("But we don't need those any more so delete them all")
    del_term, del_rev = client.delete("a", end="z")
    client.tx_status(del_term, del_rev, wait=False)

    print()
    print("Check the status of the commit")
    client.tx_status(del_term, del_rev)

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
