#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Benchmark verifying a local receipt.
"""

import base64
import hashlib
import json
import timeit

import ccf.receipt  # type: ignore
import etcd_pb2  # type: ignore
import lskvserver_pb2  # type: ignore
from cryptography.x509 import load_pem_x509_certificate  # type: ignore
from google.protobuf.json_format import ParseDict


# pylint: disable=too-many-arguments
# pylint: disable=too-many-locals
def check_receipt(
    req_type: str, request, response, receipt, receipt_json, service_cert
):
    """
    Check a receipt for a request and response.
    """
    # pylint: disable=duplicate-code
    receipt = receipt.receipt
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

    proof = receipt_json["receipt"]["txReceipt"]["proof"]
    root = ccf.receipt.root(leaf, proof)

    signature = base64.b64encode(signature).decode()
    ccf.receipt.verify(root, signature, node_cert)

    # receipt is valid, check if it matches our claims too
    claims = lskvserver_pb2.ReceiptClaims()
    getattr(claims, f"request_{req_type}").CopyFrom(request)
    getattr(claims, f"response_{req_type}").CopyFrom(response)
    claims_ser = claims.SerializeToString()
    claims_digest_calculated = hashlib.sha256(claims_ser).hexdigest()
    assert claims_digest == claims_digest_calculated

    ccf.receipt.check_endorsement(node_cert, service_cert)


def check_json_receipt(req_type, req, res, receipt, service_cert):
    """
    Check a receipt obtained in JSON form.
    """
    req = json.loads(req)
    req_pb = ParseDict(req, etcd_pb2.PutRequest())
    res = json.loads(res)
    res_pb = ParseDict(res, etcd_pb2.PutResponse())
    receipt = json.loads(receipt)
    receipt_pb = ParseDict(receipt, lskvserver_pb2.GetReceiptResponse())

    check_receipt(req_type, req_pb, res_pb, receipt_pb, receipt, service_cert)


def main():
    """
    Main function to run.
    """
    iterations = 1000
    repeats = 10

    req_type = "put"
    req = '{"key":"Zm9v","value":"YmFy"}'
    # pylint: disable=line-too-long
    res = '{"header":{"cluster_id":1201806628430307423,"member_id":15247274768972111916,"revision":11,"raft_term":2}}'
    receipt = '{"header":{"clusterId":"3170697659173810570","memberId":"17617643898592276624","revision":"12","raftTerm":"2","committedRevision":"12","committedRaftTerm":"2"},"receipt":{"cert":"-----BEGIN CERTIFICATE-----\\nMIIBwjCCAUigAwIBAgIQelWMyA4HX9YNRNHbjBB+GjAKBggqhkjOPQQDAzAWMRQw\\nEgYDVQQDDAtDQ0YgTmV0d29yazAeFw0yMzAxMTAxMTA4MDFaFw0yMzA0MTAxMTA4\\nMDBaMBMxETAPBgNVBAMMCENDRiBOb2RlMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAE\\nRcyck/p0JwM2vzGWxZwre3KF6HZWaC1pKDgBXCmOzLQ8FkOpiLiCdbiKum4wXZUB\\ncFRZXhBB0aFqPuLBlJrhF/EsDHZXw3q55cc1vJwQA6B8xqZpI5EeHBHzf/5nhVCt\\no14wXDAJBgNVHRMEAjAAMB0GA1UdDgQWBBSUkeYJQCUK2zRePcyb3ijK4joAzjAf\\nBgNVHSMEGDAWgBS70Mmt6puVhK8amGjMh9N8IHgPMDAPBgNVHREECDAGhwR/AAAB\\nMAoGCCqGSM49BAMDA2gAMGUCMQCr2zslxIrmzZua/6cVjWMMHTQsFWQQWqIEMpnN\\nt1QPC8H8kXmObnUBLnZ7xzPxLAICMAlui+wqJ2T781mlb9srf1ZB+LA4jUTCMa7/\\nRetTCm6wS4NSw2KODmt/awa11e6sUg==\\n-----END CERTIFICATE-----\\n","signature":"MGUCMB/QRsaoEmWwn5lf9E/7Suct4zsUCAoFr06wqL6mMd2+0VfH6WtfAGj0grSOjeheaAIxAPp8pKiQg8m/A9ykTq4JmkrNfgIjHpt5lx+tbBQWq7+v8EwwT2GJw6NdB/HOq1ibWA==","nodeId":"90b0eb92c8717ef4af94f2ad35dad1d0197c8dd9e9c46c2444cd0dced76780db","txReceipt":{"leafComponents":{"claimsDigest":"1e2ce1004f14e362833d5791b3d9702468d4a276665606349e9afb58b45365bd","commitEvidence":"ce:2.11:c296e4e2f3541ad12dd3cc7d90682f06a4ef6bb6fe78c97da227fccadb213ba9","writeSetDigest":"0dcbe265fd4844cf8e191df4edf8b359da18aa25d61a5d8927541f43b5e1851f"},"proof":[{"left":"6bc6a9ca7318c9c5464ad52a23761f2088090ae4632b33472b262e087bdf5e95"},{"left":"14ca017e27abc6e1e7713419c46b902b4d4926bc8639a92a916894ce83090a15"},{"left":"bf45d3693fe0bb96f73532dfe74bb1134a76c89bd6d113c4aaef3afa12e194d5"}]}}}'
    service_cert = load_pem_x509_certificate(
        """-----BEGIN CERTIFICATE-----
MIIBuDCCAT6gAwIBAgIRALGT6aKJj03G0glrrTxVumAwCgYIKoZIzj0EAwMwFjEU
MBIGA1UEAwwLQ0NGIE5ldHdvcmswHhcNMjMwMTEwMTEwODAxWhcNMjMwNDEwMTEw
ODAwWjAWMRQwEgYDVQQDDAtDQ0YgTmV0d29yazB2MBAGByqGSM49AgEGBSuBBAAi
A2IABBUSXLZ/qHxuDio17jtXUzo0fbi8x0+nbaYRMV1sam48OmMWzKqcXjiPPxht
JlefGs4011X4btVFvK7sJtpC7nj36RdwPSh7dsozjlRKmJo73yeMreSq7DoIWILi
De98G6NQME4wDAYDVR0TBAUwAwEB/zAdBgNVHQ4EFgQUu9DJreqblYSvGphozIfT
fCB4DzAwHwYDVR0jBBgwFoAUu9DJreqblYSvGphozIfTfCB4DzAwCgYIKoZIzj0E
AwMDaAAwZQIxAM2LxMnWaLDtGAMEMqaH03HaZV0CnY+s3uRkp7mCElcfMAFXY2vB
CW1ZOzn7qIUvBgIwYDcYqeN8Ox9y9ktgpLEkvdiRK6OLIF4dxnsQJ/ORjSNLPyYx
RuXUu+yl3EgtEgvw
-----END CERTIFICATE-----""".encode()
    )

    print(
        f"Timing receipt verification with {iterations} iterations and {repeats} repeats"
    )

    durations = timeit.Timer(
        lambda: check_json_receipt(req_type, req, res, receipt, service_cert)
    ).repeat(number=iterations, repeat=repeats)

    for duration in durations:
        print(
            f"Took {duration} seconds to complete {iterations} iterations, on average {duration/iterations} s/iter"
        )

    print()
    print(
        f"Average duration to complete {iterations} iterations:",
        sum(durations) / len(durations),
        "seconds",
    )
    ms_per_iter = ((sum(durations) / len(durations)) / iterations) * 1000
    print(
        "Average duration per iteration ",
        ms_per_iter,
        "milliseconds",
    )
    print("Throughput:", 1000 / ms_per_iter)


if __name__ == "__main__":
    main()
