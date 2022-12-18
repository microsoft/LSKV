# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Common utils for testing.
"""

import base64
import os
import time
from http import HTTPStatus
from subprocess import PIPE, Popen
from typing import Any, Dict, List

import httpx
import pytest
import typing_extensions
from loguru import logger

# pylint: disable=import-error
from lskv import governance  # type: ignore


class Sandbox:
    """
    Run the sandbox with lskv loaded.
    """

    def __init__(self, http2: bool):
        self.nodes = 1
        self.port = 8000
        self.http_version = 2 if http2 else 1
        self.proc = None

    def __enter__(self):
        self.proc = self.spawn()

    def __exit__(
        self, ex_type, ex_value, ex_traceback
    ) -> typing_extensions.Literal[False]:
        if self.proc:
            logger.info("terminating store process")
            self.proc.terminate()
            # give it a second to shutdown
            time.sleep(1)
            if not self.proc.poll():
                # process is still running, kill it
                logger.info("killing store process")
                self.proc.kill()
            self.proc.wait()
            logger.info("stopped")

        return False

    def wait_for_ready(self) -> bool:
        """
        Wait for the datastore to be ready to accept requests.
        """
        return self._wait_for_ready(self.port)

    # pylint: disable=duplicate-code
    def _wait_for_ready(self, port: int, tries=60) -> bool:
        client = self.etcdctl_client()
        client += ["get", "missing key"]
        if self.http_version == 1:
            client = [
                "curl",
                "--silent",
                "--cacert",
                self.cacert(),
                "--cert",
                self.cert(),
                "--key",
                self.key(),
                "-X",
                "POST",
                f"https://127.0.0.1:{self.port}/v3/kv/range",
                "-d",
                '{"key":"bWlzc2luZyBrZXkK"}',
                "-H",
                "Content-Type: application/json",
            ]

        for i in range(0, tries):
            logger.debug("running ready check with cmd {}", client)
            # pylint: disable=consider-using-with
            proc = Popen(client, stdout=PIPE)
            if proc.wait() == 0:
                out = proc.stdout
                if out:
                    outlines = out.readlines()
                    if "revision" in "\n".join(map(str, outlines)):
                        logger.info(
                            "finished waiting for port ({}) to be open, try {}", port, i
                        )
                        return True
                    logger.warning("output didn't match: {}", outlines)
            logger.debug("waiting for port ({}) to be open, try {}", port, i)
            time.sleep(1)
        logger.error("took too long waiting for port {} ({}s)", port, tries)
        return False

    def spawn(self) -> Popen:
        """
        Spawn a new sandbox instance.
        """
        with open(
            os.path.join(self.output_dir(), "node.out"), "w", encoding="utf-8"
        ) as out:
            with open(
                os.path.join(self.output_dir(), "node.err"),
                "w",
                encoding="utf-8",
            ) as err:
                libargs = ["build/liblskv.virtual.so", "-e", "virtual", "-t", "virtual"]
                env = os.environ.copy()
                env["VENV_DIR"] = os.path.join(os.getcwd(), ".venv")
                nodes = []
                for i in range(self.nodes):
                    nodes += ["--node", f"local://127.0.0.1:{self.port+i}"]
                kvs_cmd = (
                    ["/opt/ccf_virtual/bin/sandbox.sh", "-p"]
                    + libargs
                    + [
                        "--workspace",
                        self.workspace(),
                        "--verbose",
                    ]
                    + nodes
                )
                if self.http_version == 2:
                    kvs_cmd += ["--http2"]
                logger.info("spawning lskv: {}", kvs_cmd)
                return Popen(kvs_cmd, stdout=out, stderr=err, env=env)

    def output_dir(self) -> str:
        """
        Return the output directory for this sandbox run.
        """
        return "tests"

    def workspace(self):
        """
        Return the workspace directory for this store.
        """
        return os.path.join(os.getcwd(), self.output_dir(), "workspace")

    def cacert(self) -> str:
        """
        Return the path to the CA certificate.
        """
        return f"{self.workspace()}/sandbox_common/service_cert.pem"

    def cert(self) -> str:
        """
        Return the path to the client certificate.
        """
        return f"{self.workspace()}/sandbox_common/user0_cert.pem"

    def key(self) -> str:
        """
        Return the path to the key for the client certificate.
        """
        return f"{self.workspace()}/sandbox_common/user0_privk.pem"

    def member0_cert(self) -> str:
        """
        Return the path to the CA certificate.
        """
        return f"{self.workspace()}/sandbox_common/member0_cert.pem"

    def member0_key(self) -> str:
        """
        Return the path to the CA certificate.
        """
        return f"{self.workspace()}/sandbox_common/member0_privk.pem"

    def etcdctl_client(self) -> List[str]:
        """
        Get the etcdctl client command for this datastore.
        """
        return [
            "bin/etcdctl",
            "--endpoints",
            f"https://127.0.0.1:{self.port}",
            "--cacert",
            self.cacert(),
            "--cert",
            self.cert(),
            "--key",
            self.key(),
        ]


@pytest.fixture(name="sandbox", scope="module")
def fixture_sandbox():
    """
    Start the sandbox and wait to be ready.
    """
    sandbox = Sandbox(http2=False)
    with sandbox:
        ready = sandbox.wait_for_ready()
        if ready:
            # setup new constitution
            # this is needed since the ccf sandbox doesn't take a set of constitution files yet
            gov_client = governance.Client(
                "127.0.0.1:8000",
                sandbox.cacert(),
                sandbox.member0_key(),
                sandbox.member0_cert(),
            )
            proposal = governance.Proposal()
            # pylint: disable=duplicate-code
            proposal.set_constitution(
                [
                    "constitution/actions.js",
                    "constitution/apply.js",
                    "constitution/resolve.js",
                    "constitution/validate.js",
                ]
            )
            res = gov_client.propose(proposal)
            if res.state != "Accepted":
                gov_client.accept(res.proposal_id)

            yield sandbox
        else:
            raise Exception("failed to prepare the sandbox")


@pytest.fixture(name="http1_client", scope="module")
def fixture_http1_client(sandbox):
    """
    Make a http1 client for the sandbox.
    """
    cacert = sandbox.cacert()
    client_cert = (sandbox.cert(), sandbox.key())
    with httpx.Client(
        http2=False, verify=cacert, cert=client_cert, base_url="https://127.0.0.1:8000"
    ) as client:
        yield HttpClient(client)


@pytest.fixture(name="http1_client_unauthenticated", scope="module")
def fixture_http1_client_unauthenticated(sandbox):
    """
    Make an unauthenticated http1 client for the sandbox.
    """
    cacert = sandbox.cacert()
    with httpx.Client(
        http2=False, verify=cacert, base_url="https://127.0.0.1:8000"
    ) as client:
        yield HttpClient(client)


@pytest.fixture(name="governance_client", scope="module")
def fixture_governance_client(sandbox):
    """
    Make a governance client for the sandbox.
    """
    return governance.Client(
        "127.0.0.1:8000",
        sandbox.cacert(),
        sandbox.member0_key(),
        sandbox.member0_cert(),
    )


def b64encode(in_str: str) -> str:
    """
    Base64 encode a string.
    """
    return base64.b64encode(in_str.encode("utf-8")).decode("utf-8")


def b64decode(in_str: str) -> str:
    """
    Base64 decode a string.
    """
    return base64.b64decode(in_str).decode("utf-8")


class HttpClient:
    """
    A raw http client for communicating with lskv over json.
    """

    def __init__(self, client: httpx.Client):
        """
        Create a new http client.
        """
        self.client = client

    def wait_for_commit(self, term: int, rev: int, tries=100) -> bool:
        """
        Wait for a commit to be successful.
        """
        i = 0
        while True:
            i += 1
            tx_status = self.tx_status(term, rev)
            logger.debug("tx_status: {}", tx_status)
            if tx_status.status_code == HTTPStatus.OK:
                body = tx_status.json()
                if "status" in body:
                    status = body["status"]
                    logger.debug("tx_status.status: {}", status)
                    if status == "Unknown":
                        pass
                    elif status == "Pending":
                        pass
                    elif status == "Committed":
                        return True
                    elif status == "Invalid":
                        return False
            if i > tries:
                raise Exception("failed to wait for commit")
            time.sleep(0.1)

    def get(self, key: str, range_end: str = "", rev: int = 0):
        """
        Perform a get operation on lskv.
        """
        logger.info("Get: {} {} {}", key, range_end, rev)
        j: Dict[str, Any] = {"key": b64encode(key)}
        if range_end:
            j["range_end"] = b64encode(range_end)
        if rev:
            j["revision"] = rev
        return self.client.post("/v3/kv/range", json=j)

    def put(self, key: str, value: str, lease_id: int = 0):
        """
        Perform a put operation on lskv.
        """
        logger.info("Put: {} {} {}", key, value, lease_id)
        j: Dict[str, Any] = {"key": b64encode(key), "value": b64encode(value)}
        if lease_id:
            j["lease"] = lease_id
        return self.client.post("/v3/kv/put", json=j)

    def delete(self, key: str, range_end: str = ""):
        """
        Perform a delete operation on lskv.
        """
        logger.info("Delete: {} {}", key, range_end)
        j = {"key": b64encode(key)}
        if range_end:
            j["range_end"] = b64encode(range_end)
        return self.client.post("/v3/kv/delete_range", json=j)

    def compact(self, rev: int):
        """
        Compact the KV store at the given revision
        """
        logger.info("Compact: {}", rev)
        j = {"revision": rev}
        return self.client.post("/v3/kv/compact", json=j)

    def lease_grant(self, ttl: int = 60):
        """
        Perform a lease grant operation.
        """
        logger.info("LeaseGrant: {}", ttl)
        j = {"TTL": ttl}
        return self.client.post("/v3/lease/grant", json=j)

    def lease_revoke(self, lease_id: str):
        """
        Perform a lease revoke operation.
        """
        logger.info("LeaseRevoke: {}", lease_id)
        j = {"ID": lease_id}
        return self.client.post("/v3/lease/revoke", json=j)

    def lease_keep_alive(self, lease_id: str):
        """
        Perform a lease keep_alive operation.
        """
        logger.info("LeaseKeepAlive: {}", lease_id)
        j = {"ID": lease_id}
        return self.client.post("/v3/lease/keepalive", json=j)

    def tx_status(self, term: int, rev: int):
        """
        Check the status of a transaction.
        """
        logger.info("TxStatus: {} {}", term, rev)
        j: Dict[str, Any] = {"raftTerm": term, "revision": rev}
        return self.client.post("/v3/maintenance/tx_status", json=j)

    def status(self):
        """
        Get the status of LSKV.
        """
        logger.info("Status")
        return self.client.post("/v3/maintenance/status", json={})

    def raw(self) -> httpx.Client:
        """
        Get the raw client.
        """
        return self.client
