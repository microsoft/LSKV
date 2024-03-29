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
    b64encode,
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
    res = http1_client_unauthenticated.put("foo", "bar", check=False)
    assert res.status_code == HTTPStatus.UNAUTHORIZED
    res = http1_client_unauthenticated.get("foo", check=False)
    assert res.status_code == HTTPStatus.UNAUTHORIZED
    res = http1_client_unauthenticated.delete("foo", check=False)
    assert res.status_code == HTTPStatus.UNAUTHORIZED


# pylint: disable=redefined-outer-name
def test_kv_latest(http1_client):
    """
    Test that the KV system works with the optimistic queries
    """
    res = http1_client.put("foo", "bar")
    put_rev = res.json()["header"]["revision"]

    res = http1_client.get("foo")
    kvs = res.json()["kvs"]
    assert b64decode(kvs[0]["key"]) == "foo"
    assert b64decode(kvs[0]["value"]) == "bar"
    assert kvs[0]["createRevision"] == str(put_rev)
    assert kvs[0]["modRevision"] == str(put_rev)
    assert kvs[0]["version"] == "1"

    # writing to it again updates the revision and version
    res = http1_client.put("foo", "bar")
    update_rev = res.json()["header"]["revision"]

    res = http1_client.get("foo")
    kvs = res.json()["kvs"]
    assert b64decode(kvs[0]["key"]) == "foo"
    assert b64decode(kvs[0]["value"]) == "bar"
    assert kvs[0]["createRevision"] == str(put_rev)
    assert kvs[0]["modRevision"] == str(update_rev)
    assert kvs[0]["version"] == "2"

    # then we can delete it
    res = http1_client.delete("foo")

    # and not see it any more
    res = http1_client.get("foo")
    assert "kvs" not in res.json()

    # then create it again and it should have a new version and create_revision
    res = http1_client.put("foo", "bar")
    put_rev = res.json()["header"]["revision"]

    res = http1_client.get("foo")
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
        rev = int(res.json()["header"]["revision"])
        term = int(res.json()["header"]["raftTerm"])
        revisions.append((rev, term))

    # should probably wait for commit to do this
    rev, term = revisions[-1]
    http1_client.wait_for_commit(term, rev)

    create_rev = revisions[0][0]
    for i, (rev, term) in enumerate(revisions):
        res = http1_client.get("fooh", rev=rev)
        kvs = res.json()["kvs"]
        assert b64decode(kvs[0]["key"]) == "fooh"
        assert b64decode(kvs[0]["value"]) == f"bar{i}"
        assert kvs[0]["createRevision"] == str(create_rev)
        assert kvs[0]["modRevision"] == str(rev)
        assert kvs[0]["version"] == str(i + 1)

    res = http1_client.delete("fooh")
    deleted_rev = int(res.json()["header"]["revision"])

    for i, (rev, term) in enumerate(revisions):
        # still there
        res = http1_client.get("fooh", rev=rev)
        kvs = res.json()["kvs"]
        assert b64decode(kvs[0]["key"]) == "fooh"
        assert b64decode(kvs[0]["value"]) == f"bar{i}"
        assert kvs[0]["createRevision"] == str(create_rev)
        assert kvs[0]["modRevision"] == str(rev)
        assert kvs[0]["version"] == str(i + 1)

    # but we can't see it in the historical keyspace anymore
    res = http1_client.get("fooh", rev=deleted_rev)
    assert "kvs" not in res.json()  # fields with default values are not included
    assert "count" not in res.json()  # fields with default values are not included


# pylint: disable=redefined-outer-name
def test_kv_compaction(http1_client):
    """
    Test that compacted entries aren't accessible.
    """
    revisions = []
    for i in range(5):
        res = http1_client.put("foocompact", f"bar{i}")
        hdr = res.json()["header"]
        rev = int(hdr["revision"])
        term = int(hdr["raftTerm"])
        revisions.append((rev, term))

    rev, term = revisions[-1]
    http1_client.wait_for_commit(term, rev)

    # remove earlier items
    res = http1_client.compact(revisions[2][0])

    # check that we can't access all of them
    for i in range(5):
        res = http1_client.get("foocompact", rev=revisions[i][0])
        success = revisions[i][0] >= revisions[2][0]
        if success:
            assert int(res.json()["count"]) == 1
        else:
            assert "count" not in res.json()


def test_status_version(http1_client):
    """
    Test that the status endpoint returns the version.
    """
    res = http1_client.status()
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
    _, proto = http1_client.lease_grant()
    lease_id = proto.ID

    # then create a key with it
    http1_client.put(key, "present", lease_id=lease_id)

    # then get the key to check it has the lease id set
    res = http1_client.get(key)
    assert int(res.json()["kvs"][0]["lease"]) == lease_id

    # revoke the lease
    http1_client.lease_revoke(lease_id)

    # get the key again to see if it exists
    res = http1_client.get(key)
    assert "kvs" not in res.json()


# pylint: disable=redefined-outer-name
def test_lease(http1_client):
    """
    Test lease creation, revocation and keep-alive.
    """
    # creating a lease works
    _, proto = http1_client.lease_grant()
    lease_id = proto.ID

    # then we can keep that lease alive (extending the ttl)
    http1_client.lease_keep_alive(lease_id)

    # and explicitly revoke the lease
    http1_client.lease_revoke(lease_id)

    # but we can't keep a revoked lease alive
    res, proto = http1_client.lease_keep_alive(lease_id, check=False)
    logger.info("res: {} {}", res.status_code, res.text)
    assert res.status_code == 400

    # and we can't revoke lease that wasn't active (or known)
    missing_id = "002"
    http1_client.lease_revoke(missing_id)


def test_tx_status(http1_client):
    """
    Test custom tx_status endpoint.
    """
    res = http1_client.put("footx", "bar")
    j = res.json()
    term = j["header"]["raftTerm"]
    rev = j["header"]["revision"]
    http1_client.wait_for_commit(term, rev)

    res = http1_client.tx_status(term, rev)
    status = res.json()["status"]
    # the node needs time to commit, but that may have happened already
    assert status in ["Pending", "Committed"]

    res = http1_client.tx_status(term, 100000)
    # a tx far in the future may have been submitted by another node
    assert "status" not in res.json()  # missing status means Unknown

    res = http1_client.tx_status(int(term) + 1, int(rev) - 1)
    status = res.json()["status"]
    assert status == "Invalid"


def test_public_prefix(governance_client, http1_client, sandbox):
    """
    Test the constitution action for public prefixes.
    """
    prefix = "mysecretprefix"
    res = http1_client.put(f"{prefix}/test", "my secret")
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

    # removing an existing prefix is ok
    proposal = governance.Proposal()
    proposal.remove_public_prefix(prefix)
    res = governance_client.propose(proposal)
    proposal_id = res.proposal_id
    governance_client.accept(proposal_id)

    # setting a new key now doesn't end up public
    res = http1_client.put(f"{prefix}/test", "my secret")
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


def test_range_limit(http1_client):
    """
    Test the limit arg on range queries.
    """
    http1_client.put("range_limit1", "val")
    http1_client.put("range_limit2", "val")
    res = http1_client.get("range_limit", range_end="range_limit4")
    assert len(res.json()["kvs"]) == 2
    assert res.json()["count"] == "2"

    res = http1_client.get("range_limit", range_end="range_limit4", limit=1)
    assert len(res.json()["kvs"]) == 1
    assert res.json()["count"] == "1"
    assert res.json()["kvs"][0]["key"] == b64encode("range_limit1")
