# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test a single node
"""

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
