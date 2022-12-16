# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test a single node
"""

import os
import re
from http import HTTPStatus

# pylint: disable=import-error
import ccf.ledger  # type: ignore
from loguru import logger

# pylint: disable=unused-import
# pylint: disable=no-name-in-module
from test_common import (
    b64decode,
    fixture_governance_client,
    fixture_http1_client,
    fixture_http1_client_unauthenticated,
    fixture_sandbox,
)

# pylint: disable=import-error
from lskv import governance  # type: ignore


# pylint: disable=redefined-outer-name
def test_starts(http1_client):
    """
    Test that the sandbox starts.
    """
    res = http1_client.raw().get("api")
    assert res.status_code == HTTPStatus.OK


# pylint: disable=redefined-outer-name
def test_unauthenticated(http1_client_unauthenticated):
    """
    Test that the unauthenticated users can't interact.
    """
    res = http1_client_unauthenticated.put("foo", "bar")
    assert res.status_code == HTTPStatus.UNAUTHORIZED
    res = http1_client_unauthenticated.get("foo")
    assert res.status_code == HTTPStatus.UNAUTHORIZED
    res = http1_client_unauthenticated.delete("foo")
    assert res.status_code == HTTPStatus.UNAUTHORIZED


# pylint: disable=redefined-outer-name
def test_kv_latest(http1_client):
    """
    Test that the KV system works with the optimistic queries
    """
    res = http1_client.put("foo", "bar")
    check_response(res)
    put_rev = res.json()["header"]["revision"]

    res = http1_client.get("foo")
    check_response(res)
    kvs = res.json()["kvs"]
    assert b64decode(kvs[0]["key"]) == "foo"
    assert b64decode(kvs[0]["value"]) == "bar"
    assert kvs[0]["createRevision"] == str(put_rev)
    assert kvs[0]["modRevision"] == str(put_rev)
    assert kvs[0]["version"] == "1"

    # writing to it again updates the revision and version
    res = http1_client.put("foo", "bar")
    check_response(res)
    update_rev = res.json()["header"]["revision"]

    res = http1_client.get("foo")
    check_response(res)
    kvs = res.json()["kvs"]
    assert b64decode(kvs[0]["key"]) == "foo"
    assert b64decode(kvs[0]["value"]) == "bar"
    assert kvs[0]["createRevision"] == str(put_rev)
    assert kvs[0]["modRevision"] == str(update_rev)
    assert kvs[0]["version"] == "2"

    # then we can delete it
    res = http1_client.delete("foo")
    check_response(res)

    # and not see it any more
    res = http1_client.get("foo")
    check_response(res)
    assert "kvs" not in res.json()

    # then create it again and it should have a new version and create_revision
    res = http1_client.put("foo", "bar")
    check_response(res)
    put_rev = res.json()["header"]["revision"]

    res = http1_client.get("foo")
    check_response(res)
    kvs = res.json()["kvs"]
    assert b64decode(kvs[0]["key"]) == "foo"
    assert b64decode(kvs[0]["value"]) == "bar"
    assert kvs[0]["createRevision"] == str(put_rev)
    assert kvs[0]["modRevision"] == str(put_rev)
    assert kvs[0]["version"] == "1"


# pylint: disable=redefined-outer-name
def test_kv_historical(http1_client):
    """
    Test that historical queries work.
    """
    revisions = []
    for i in range(5):
        res = http1_client.put("fooh", f"bar{i}")
        check_response(res)
        rev = int(res.json()["header"]["revision"])
        term = int(res.json()["header"]["raftTerm"])
        revisions.append((rev, term))

    # should probably wait for commit to do this
    rev, term = revisions[-1]
    http1_client.wait_for_commit(term, rev)

    create_rev = revisions[0][0]
    for i, (rev, term) in enumerate(revisions):
        res = http1_client.get("fooh", rev=rev)
        check_response(res)
        kvs = res.json()["kvs"]
        assert b64decode(kvs[0]["key"]) == "fooh"
        assert b64decode(kvs[0]["value"]) == f"bar{i}"
        assert kvs[0]["createRevision"] == str(create_rev)
        assert kvs[0]["modRevision"] == str(rev)
        assert kvs[0]["version"] == str(i + 1)

    res = http1_client.delete("fooh")
    check_response(res)
    deleted_rev = int(res.json()["header"]["revision"])

    for i, (rev, term) in enumerate(revisions):
        # still there
        res = http1_client.get("fooh", rev=rev)
        check_response(res)
        kvs = res.json()["kvs"]
        assert b64decode(kvs[0]["key"]) == "fooh"
        assert b64decode(kvs[0]["value"]) == f"bar{i}"
        assert kvs[0]["createRevision"] == str(create_rev)
        assert kvs[0]["modRevision"] == str(rev)
        assert kvs[0]["version"] == str(i + 1)

    # but we can't see it in the historical keyspace anymore
    res = http1_client.get("fooh", rev=deleted_rev)
    check_response(res)
    assert "kvs" not in res.json()  # fields with default values are not included
    assert "count" not in res.json()  # fields with default values are not included


def test_status_version(http1_client):
    """
    Test that the status endpoint returns the version.
    """
    res = http1_client.status()
    check_response(res)
    version = res.json()["version"]
    version_re = r"^\d+\.\d+\.\d+(-.*)?$"
    assert re.match(version_re, version)


# pylint: disable=redefined-outer-name
def test_lease_kv(http1_client):
    """
    Test lease attachment to keys.
    """
    key = __name__
    # create a lease
    res = http1_client.lease_grant()
    check_response(res)
    lease_id = res.json()["ID"]

    # then create a key with it
    res = http1_client.put(key, "present", lease_id=lease_id)
    check_response(res)

    # then get the key to check it has the lease id set
    res = http1_client.get(key)
    check_response(res)
    assert res.json()["kvs"][0]["lease"] == lease_id

    # revoke the lease
    res = http1_client.lease_revoke(lease_id)
    check_response(res)

    # get the key again to see if it exists
    res = http1_client.get(key)
    check_response(res)
    assert "kvs" not in res.json()


# pylint: disable=redefined-outer-name
def test_lease(http1_client):
    """
    Test lease creation, revocation and keep-alive.
    """
    # creating a lease works
    res = http1_client.lease_grant()
    check_response(res)
    lease_id = res.json()["ID"]

    # then we can keep that lease alive (extending the ttl)
    res = http1_client.lease_keep_alive(lease_id)
    check_response(res)

    # and explicitly revoke the lease
    res = http1_client.lease_revoke(lease_id)
    check_response(res)

    # but we can't keep a revoked lease alive
    res = http1_client.lease_keep_alive(lease_id)
    logger.info("res: {} {}", res.status_code, res.text)
    assert res.status_code == 400

    # and we can't revoke lease that wasn't active (or known)
    missing_id = "002"
    res = http1_client.lease_revoke(missing_id)
    check_response(res)


def test_tx_status(http1_client):
    """
    Test custom tx_status endpoint.
    """
    res = http1_client.put("footx", "bar")
    check_response(res)
    j = res.json()
    term = j["header"]["raftTerm"]
    rev = j["header"]["revision"]
    http1_client.wait_for_commit(term, rev)

    res = http1_client.tx_status(term, rev)
    check_response(res)
    status = res.json()["status"]
    # the node needs time to commit, but that may have happened already
    assert status in ["Pending", "Committed"]

    res = http1_client.tx_status(term, 100000)
    check_response(res)
    # a tx far in the future may have been submitted by another node
    assert "status" not in res.json()  # missing status means Unknown

    res = http1_client.tx_status(int(term) + 1, int(rev) - 1)
    check_response(res)
    status = res.json()["status"]
    assert status == "Invalid"


def test_public_prefix(governance_client, http1_client, sandbox):
    """
    Test the constitution action for public prefixes.
    """
    prefix = "mysecretprefix"
    res = http1_client.put(f"{prefix}/test", "my secret")
    check_response(res)
    term = int(res.json()["header"]["raftTerm"])
    rev = int(res.json()["header"]["revision"])
    http1_client.wait_for_commit(term, rev)

    ledger = ccf.ledger.Ledger(
        [os.path.join(sandbox.workspace(), "sandbox_0", "0.ledger")],
        committed_only=False,
    )
    txn = ledger.get_transaction(rev)
    public_domain = txn.get_public_domain()
    assert len(public_domain.get_tables()) == 0

    # set a secret prefix
    proposal = governance.Proposal()
    proposal.set_public_prefix(prefix)
    res = governance_client.propose(proposal)
    proposal_id = res.proposal_id
    governance_client.accept(proposal_id)

    res = http1_client.put(f"{prefix}/test", "my secret")
    check_response(res)
    term = int(res.json()["header"]["raftTerm"])
    rev = int(res.json()["header"]["revision"])
    http1_client.wait_for_commit(term, rev)

    ledger = ccf.ledger.Ledger(
        [os.path.join(sandbox.workspace(), "sandbox_0", "0.ledger")],
        committed_only=False,
    )
    txn = ledger.get_transaction(rev)
    public_domain = txn.get_public_domain()
    assert len(public_domain.get_tables()) == 1

    # setting an existing prefix is ok
    proposal = governance.Proposal()
    proposal.set_public_prefix(prefix)
    res = governance_client.propose(proposal)
    proposal_id = res.proposal_id
    governance_client.accept(proposal_id)

    # removing an existing prefix is ok
    proposal = governance.Proposal()
    proposal.remove_public_prefix(prefix)
    res = governance_client.propose(proposal)
    proposal_id = res.proposal_id
    governance_client.accept(proposal_id)

    # and removing one that doesn't exist is ok too
    proposal = governance.Proposal()
    proposal.remove_public_prefix(prefix)
    res = governance_client.propose(proposal)
    proposal_id = res.proposal_id
    governance_client.accept(proposal_id)

    # setting a new key now doesn't end up public
    res = http1_client.put(f"{prefix}/test", "my secret")
    check_response(res)
    term = int(res.json()["header"]["raftTerm"])
    rev = int(res.json()["header"]["revision"])
    http1_client.wait_for_commit(term, rev)

    ledger = ccf.ledger.Ledger(
        [os.path.join(sandbox.workspace(), "sandbox_0", "0.ledger")],
        committed_only=False,
    )
    txn = ledger.get_transaction(rev)
    public_domain = txn.get_public_domain()
    assert len(public_domain.get_tables()) == 0


def check_response(res):
    """
    Check a response to be success.
    """
    logger.info("res: {} {}", res.status_code, res.text)
    assert res.status_code == HTTPStatus.OK
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
