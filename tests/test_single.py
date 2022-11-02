# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test a single node
"""

# pylint: disable=unused-import
# pylint: disable=no-name-in-module
from test_common import b64decode, fixture_http1_client, fixture_sandbox


# pylint: disable=redefined-outer-name
def test_starts(http1_client):
    """
    Test that the sandbox starts.
    """
    res = http1_client.raw().get("api")
    assert res.status_code == 200


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
