# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Common utils for testing.
"""

import base64
import hashlib
import http
import os
import time
from http import HTTPStatus
from subprocess import PIPE, Popen
from typing import List, Dict, Any

import ccf.receipt  # type: ignore

# pylint: disable=import-error
import etcd_pb2  # type: ignore
import httpx

# pylint: disable=import-error
import lskvserver_pb2  # type: ignore
import pytest
import typing_extensions
from cryptography.x509 import load_pem_x509_certificate  # type: ignore
from google.protobuf.json_format import MessageToDict, ParseDict
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
            raise RuntimeError("failed to prepare the sandbox")


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
                raise RuntimeError("failed to wait for commit")
            time.sleep(0.1)

    # pylint: disable=too-many-arguments
    def get(
        self, key: str, range_end: str = "", rev: int = 0, limit: int = 0, check=True
    ):
        """
        Perform a get operation on lskv.
        """
        logger.info("Get: {} {} {} {}", key, range_end, rev, limit)
        req = etcd_pb2.RangeRequest()
        req.key = key.encode("utf-8")
        if range_end:
            req.range_end = range_end.encode("utf-8")
        if rev:
            req.revision = rev
        if limit:
            req.limit = limit
        j = MessageToDict(req)
        res = self.client.post("/v3/kv/range", json=j)
        if check:
            check_response(res)
        return res

    # pylint: disable=too-many-arguments
    def put(
        self,
        key: str,
        value: str,
        lease_id: int = 0,
        wait_for_commit: bool = True,
        check_receipt=True,
        check=True,
    ):
        """
        Perform a put operation on lskv.
        """
        logger.info("Put: {} {}", key, value)
        req = etcd_pb2.PutRequest()
        req.key = key.encode("utf-8")
        req.value = value.encode("utf-8")
        if lease_id:
            req.lease = lease_id
        j = MessageToDict(req)
        res = self.client.post("/v3/kv/put", json=j)
        if check:
            check_response(res)
            if wait_for_commit:
                rev, term = extract_rev_term(res)
                self.wait_for_commit(term, rev)
            if check_receipt:
                res_pb = ParseDict(res.json(), etcd_pb2.PutResponse())
                self.check_receipt("put", req, res_pb)
        return res

    # pylint: disable=too-many-arguments
    def delete(
        self,
        key: str,
        range_end: str = "",
        wait_for_commit: bool = True,
        check_receipt=True,
        check=True,
    ):
        """
        Perform a delete operation on lskv.
        """
        logger.info("Delete: {} {}", key, range_end)
        req = etcd_pb2.DeleteRangeRequest()
        req.key = key.encode("utf-8")
        if range_end:
            req.range_end = range_end.encode("utf-8")
        j = MessageToDict(req)
        res = self.client.post("/v3/kv/delete_range", json=j)
        if check:
            check_response(res)
            if wait_for_commit:
                rev, term = extract_rev_term(res)
                self.wait_for_commit(term, rev)
            if check_receipt:
                res_pb = ParseDict(res.json(), etcd_pb2.DeleteRangeResponse())
                self.check_receipt("delete_range", req, res_pb)
        return res

    def get_receipt(self, rev: int, term: int):
        """
        Get a receipt for a revision and term.
        """
        logger.info("GetReceipt: {} {}", rev, term)
        req = lskvserver_pb2.GetReceiptRequest()
        req.revision = rev
        req.raft_term = term
        j = MessageToDict(req)
        res = self.client.post(
            "/v3/receipt/get_receipt",
            json=j,
        )
        if res.status_code == http.HTTPStatus.ACCEPTED:
            logger.info("GetReceipt: ACCEPTED")
            # accepted, retry
            res = self.client.post(
                "/v3/receipt/get_receipt",
                json=j,
            )
        check_response(res)
        proto = ParseDict(res.json(), lskvserver_pb2.GetReceiptResponse())
        return (res, proto)

    def compact(self, rev: int, check=True):
        """
        Compact the KV store at the given revision
        """
        logger.info("Compact: {}", rev)
        j = {"revision": rev}
        res = self.client.post("/v3/kv/compact", json=j)
        if check:
            check_response(res)
        return res

    def lease_grant(self, ttl: int = 60):
        """
        Perform a lease grant operation.
        """
        logger.info("LeaseGrant: {}", ttl)
        j = {"TTL": ttl}
        res = self.client.post("/v3/lease/grant", json=j)
        check_response(res)
        proto = ParseDict(res.json(), etcd_pb2.LeaseGrantResponse())
        return (res, proto)

    def lease_revoke(self, lease_id: str):
        """
        Perform a lease revoke operation.
        """
        logger.info("LeaseRevoke: {}", lease_id)
        j = {"ID": lease_id}
        res = self.client.post("/v3/lease/revoke", json=j)
        check_response(res)
        proto = ParseDict(res.json(), etcd_pb2.LeaseRevokeResponse())
        return (res, proto)

    def lease_keep_alive(self, lease_id: str, check=True):
        """
        Perform a lease keep_alive operation.
        """
        logger.info("LeaseKeepAlive: {}", lease_id)
        j = {"ID": lease_id}
        res = self.client.post("/v3/lease/keepalive", json=j)
        proto = None
        if check:
            check_response(res)
            proto = ParseDict(res.json(), etcd_pb2.LeaseKeepAliveResponse())
        return (res, proto)

    def tx_status(self, term: int, rev: int, check=True):
        """
        Check the status of a transaction.
        """
        logger.info("TxStatus: {} {}", term, rev)
        j: Dict[str, Any] = {"raftTerm": term, "revision": rev}
        res = self.client.post("/v3/maintenance/tx_status", json=j)
        if check:
            check_response(res)
        return res

    def status(self):
        """
        Get the status of LSKV.
        """
        logger.info("Status")
        res = self.client.post("/v3/maintenance/status", json={})
        check_response(res)
        return res

    def raw(self) -> httpx.Client:
        """
        Get the raw client.
        """
        return self.client

    # pylint: disable=too-many-locals
    def check_receipt(self, req_type: str, request, response):
        """
        Check a receipt for a request and response.
        """
        rev, term = extract_rev_term_pb(response)
        res, proto = self.get_receipt(rev, term)

        receipt = proto.receipt
        tx_receipt = receipt.tx_receipt
        leaf_components = tx_receipt.leaf_components
        claims_digest = leaf_components.claims_digest
        write_set_digest = leaf_components.write_set_digest
        commit_evidence = leaf_components.commit_evidence

        response.ClearField("header")

        commit_evidence_digest = hashlib.sha256(commit_evidence.encode()).digest()
        leaf_parts = [
            bytes.fromhex(write_set_digest),
            commit_evidence_digest,
            bytes.fromhex(claims_digest),
        ]
        leaf = hashlib.sha256(b"".join(leaf_parts)).hexdigest()

        signature = receipt.signature
        cert = receipt.cert
        node_cert = load_pem_x509_certificate(cert.encode())

        root = ccf.receipt.root(leaf, res.json()["receipt"]["txReceipt"]["proof"])

        signature = base64.b64encode(signature).decode()
        logger.debug("verifying receipt signature:{}", signature)
        ccf.receipt.verify(root, signature, node_cert)

        # receipt is valid, check if it matches our claims too
        claims = lskvserver_pb2.ReceiptClaims()
        getattr(claims, f"request_{req_type}").CopyFrom(request)
        getattr(claims, f"response_{req_type}").CopyFrom(response)
        claims_ser = claims.SerializeToString()
        claims_digest_calculated = hashlib.sha256(claims_ser).hexdigest()
        assert claims_digest == claims_digest_calculated


def check_response(res):
    """
    Check a response to be success.
    """
    logger.info("res: {} {}", res.status_code, res.text)
    assert res.status_code == 200
    check_header(res.json())


def check_header(body):
    """
    Check the header is well-formed.
    """
    assert "header" in body
    header = body["header"]
    assert "clusterId" in header
    assert "memberId" in header
    assert "revision" in header
    assert "raftTerm" in header


def extract_rev_term(res):
    """
    Extract the revision and term from a response.
    """
    header = res.json()["header"]
    return int(header["revision"]), int(header["raftTerm"])


def extract_rev_term_pb(res):
    """
    Extract the revision and term from a pb response.
    """
    header = res.header
    return header.revision, header.raft_term
