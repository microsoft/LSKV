# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test a single node
"""

from http import HTTPStatus

from loguru import logger
import re

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

    res = http1_client.get("foo")
    check_response(res)
    assert b64decode(res.json()["kvs"][0]["key"]) == "foo"
    assert b64decode(res.json()["kvs"][0]["value"]) == "bar"

    res = http1_client.delete("foo")
    check_response(res)

    res = http1_client.get("foo")
    check_response(res)
    assert "kvs" not in res.json()


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

    for i, (rev, term) in enumerate(revisions):
        res = http1_client.get("fooh", rev=rev)
        check_response(res)
        assert b64decode(res.json()["kvs"][0]["key"]) == "fooh"
        assert b64decode(res.json()["kvs"][0]["value"]) == f"bar{i}"

    res = http1_client.delete("fooh")
    check_response(res)

    for i, (rev, term) in enumerate(revisions):
        # still there
        res = http1_client.get("fooh", rev=rev)
        check_response(res)
        assert b64decode(res.json()["kvs"][0]["key"]) == "fooh"
        assert b64decode(res.json()["kvs"][0]["value"]) == f"bar{i}"


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
