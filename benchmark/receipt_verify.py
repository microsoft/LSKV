import ccf.receipt  # type: ignore
import base64
from cryptography.x509 import load_pem_x509_certificate  # type: ignore
import etcd_pb2  # type: ignore
import lskvserver_pb2  # type: ignore
import json
import timeit
import hashlib
from loguru import logger
from google.protobuf.json_format import MessageToDict, ParseDict


def check_receipt(req_type: str, request, response, receipt, receipt_json):
    """
    Check a receipt for a request and response.
    """
    rev, term = response.header.revision, response.header.raft_term

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


def check_json_receipt(req_type, req, res, receipt):
    req = json.loads(req)
    req_pb = ParseDict(req, etcd_pb2.PutRequest())
    res = json.loads(res)
    res_pb = ParseDict(res, etcd_pb2.PutResponse())
    receipt = json.loads(receipt)
    receipt_pb = ParseDict(receipt, lskvserver_pb2.GetReceiptResponse())

    check_receipt(req_type, req_pb, res_pb, receipt_pb, receipt)


def main():
    iterations = 1000
    repeats = 10

    req_type = "put"
    req = '{"key":"YQ==","value":"Yg=="}'
    res = '{"header":{"cluster_id":1201806628430307423,"member_id":15247274768972111916,"revision":11,"raft_term":2}}'
    receipt = '{"header":{"clusterId":"1201806628430307423","memberId":"15247274768972111916","revision":"12","raftTerm":"2","committedRevision":"12","committedRaftTerm":"2"},"receipt":{"cert":"-----BEGIN CERTIFICATE-----\\nMIIBwzCCAUmgAwIBAgIRAKYlYuAhGIfcih3QDJsVfH4wCgYIKoZIzj0EAwMwFjEU\\nMBIGA1UEAwwLQ0NGIE5ldHdvcmswHhcNMjMwMTA2MTIwODM2WhcNMjMwNDA2MTIw\\nODM1WjATMREwDwYDVQQDDAhDQ0YgTm9kZTB2MBAGByqGSM49AgEGBSuBBAAiA2IA\\nBB0era6qeg/KkKhxvfJUI3bwSYToBuuAxiB1O4H/YbVoq+/j9ljf6SAPA/lEMwaB\\nUaq3Tf2GGhjIwBFQsiD7ZDpC8+UhDxzGRNrCa8kUqAvXdr2AZoGc3Bpiy812qQDL\\ncaNeMFwwCQYDVR0TBAIwADAdBgNVHQ4EFgQUZVBGS+4onlJn1H0mEQL0eOIC6U4w\\nHwYDVR0jBBgwFoAUF6/StYa1PdeEITb16OPG/LcoFl8wDwYDVR0RBAgwBocEfwAA\\nATAKBggqhkjOPQQDAwNoADBlAjEAolzbk5mSRdJ2kat0FzJgy9jzTe38BDFFZYl2\\nlhLN8CFfWkfWsEGU12ZO4HUfZz5xAjApJfoOAUg13hIpseGjFCOFVD8QlGVZVjz4\\nu91XTau+62uMBoGfLG6QDxmEjYWHzCQ=\\n-----END CERTIFICATE-----\\n","signature":"MGQCME8JI0fJqsJp0Asor/C3dQjt/b5xSQs6LF1pM7MZikPV3VSewct8Ll5POz4OqHg1UwIwQbIo9hdZjA4h1hcWUV+8OhobsnaDvAhRQ68rYb1fovt28bx/rm2LsPPzeyzbFTLq","nodeId":"2ce05b6d9e3399d3a38a740c9bb82114f75fab3c493069186767a903d4ca9cf6","txReceipt":{"leafComponents":{"claimsDigest":"7efbc55203a0e1ea810e2e8c1a9561ff650ac0d5de623b3f35f145823466edc9","commitEvidence":"ce:2.11:166dae27360e38b6657b90dca456c5ab2b805bc008a3892b274b7d2b2bb72c8a","writeSetDigest":"4d67287b7a5b6b808e9cbb84017e27a57d83d60847def8ccffe273f82c6d6a2d"},"proof":[{"left":"630a7b723504d69c95ae7ce64499f37060da2fa351f1b18d29e13f2695c5cbbb"},{"left":"3f7582f3b824d2af7a81bf106514a6c817332ea346a918c2fc45cb12c2c0cacc"},{"left":"822d9b9ead97bc353d3e044316636155650b25e1f15d819d5e07185786108d77"}]}}}'

    print(f"Timing receipt verification with {iterations} iterations and {repeats} repeats")

    durations = timeit.Timer(
        lambda: check_json_receipt(req_type, req, res, receipt)
    ).repeat(number=iterations, repeat=repeats)

    for duration in durations:
        print(f"Took {duration} seconds to complete {iterations} iterations, on average {duration/iterations} s/iter")

    print()
    print(f"Average duration to complete {iterations} iterations:", sum(durations) / len(durations), "seconds")
    print(
        "Average duration per iteration ",
        ((sum(durations) / len(durations)) / iterations) * 1000,
        "milliseconds",
    )


if __name__ == "__main__":
    main()
