# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test a single node
"""

import re
from http import HTTPStatus

from loguru import logger

# pylint: disable=unused-import
# pylint: disable=no-name-in-module
from test_common import (
    b64decode,
    fixture_http1_client,
    fixture_http1_client_unauthenticated,
    fixture_sandbox,
)


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

    res = http1_client.get("foo")
    assert b64decode(res.json()["kvs"][0]["key"]) == "foo"
    assert b64decode(res.json()["kvs"][0]["value"]) == "bar"

    res = http1_client.delete("foo")

    res = http1_client.get("foo")
    assert "kvs" not in res.json()


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

    for i, (rev, term) in enumerate(revisions):
        res = http1_client.get("fooh", rev=rev)
        assert b64decode(res.json()["kvs"][0]["key"]) == "fooh"
        assert b64decode(res.json()["kvs"][0]["value"]) == f"bar{i}"

    res = http1_client.delete("fooh")

    for i, (rev, term) in enumerate(revisions):
        # still there
        res = http1_client.get("fooh", rev=rev)
        assert b64decode(res.json()["kvs"][0]["key"]) == "fooh"
        assert b64decode(res.json()["kvs"][0]["value"]) == f"bar{i}"


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
    assert res.json()["kvs"][0]["lease"] == lease_id

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
