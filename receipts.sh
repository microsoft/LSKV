#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

header=$(./etcdctl.sh put a b -w json | jq '.header')
rev=$(echo "$header" | jq '.revision')
raft_term=$(echo "$header" | jq '.raft_term')

curl -X POST -k https://127.0.0.1:8000/v3/receipt/get_receipt -d '{"revision": "'"$rev"'", "raft_term": "'"$raft_term"'"}' -H 'content-type: application/json'
curl -X POST -k https://127.0.0.1:8000/v3/receipt/get_receipt -d '{"revision": "'"$rev"'", "raft_term": "'"$raft_term"'"}' -H 'content-type: application/json' | jq

sig_rev=$((rev + 1))
curl -X POST -k https://127.0.0.1:8000/v3/receipt/get_receipt -d '{"revision": "'"$sig_rev"'", "raft_term": "'"$raft_term"'"}' -H 'content-type: application/json'
curl -X POST -k https://127.0.0.1:8000/v3/receipt/get_receipt -d '{"revision": "'"$sig_rev"'", "raft_term": "'"$raft_term"'"}' -H 'content-type: application/json' | jq
