// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.
import { check, randomSeed } from "k6";
import http from "k6/http";
import encoding from "k6/encoding";
import exec from "k6/execution";

const rate = Number(__ENV.RATE);
const workspace = __ENV.WORKSPACE;
const preAllocatedVUs = __ENV.PRE_ALLOCATED_VUS;
const maxVUs = __ENV.MAX_VUS;
const func = __ENV.FUNC;

const duration_s = 10;

export let options = {
  tlsAuth: [
    {
      cert: open(`${workspace}/user0_cert.pem`),
      key: open(`${workspace}/user0_privk.pem`),
    },
  ],
  insecureSkipTLSVerify: true,
  scenarios: {
    default: {
      executor: "constant-arrival-rate",
      exec: func,
      rate: rate,
      duration: `${duration_s}s`,
      timeUnit: "1s",
      preAllocatedVUs: preAllocatedVUs,
      maxVUs: maxVUs,
    },
  },
};

const key0 = encoding.b64encode("key0");
const val0 = encoding.b64encode("value0");

const json_header_params = {
  headers: {
    "Content-Type": "application/json",
  },
};

const host = "https://127.0.0.1:8000";

export function setup() {
  // write a key to the store for get clients
  put_single_wait();
  randomSeed(123);

  let receipt_txids = [];
  if (func == "get_receipt") {
    console.log("setting up receipts");
    const total_requests = rate * duration_s;
    var txid = "";
    // trigger getting some cached ones too (maybe)
    for (let i = 0; i < total_requests / 2; i++) {
      // issue some writes so we have things to get receipts for
      txid = put_single();
      receipt_txids.push(txid);
    }
    wait_for_committed(txid);
  }
  return receipt_txids;
}

function check_success(response) {
  check(response, {
    "http1 is used": (r) => r.proto === "HTTP/1.1",
    "status is 200": (r) => r.status === 200,
  });
}

function check_committed(status) {
  check(status, {
    "committed within limit": (status) => status === "Committed",
  });
}

// perform a single put request at a preset key
export function put_single() {
  let payload = JSON.stringify({
    key: key0,
    value: val0,
  });

  let response = http.post(`${host}/v3/kv/put`, payload, json_header_params);

  check_success(response);

  const res = response.json();
  const header = res["header"];
  const term = header["raftTerm"];
  const rev = header["revision"];
  const txid = `${term}.${rev}`;
  return txid;
}

// check the status of a transaction id with the service
function get_tx_status(txid) {
  const response = http.get(`${host}/app/tx?transaction_id=${txid}`);
  return response.json()["status"];
}

function wait_for_committed(txid) {
  var s = "";
  const tries = 1000;
  for (let i = 0; i < tries; i++) {
    s = get_tx_status(txid);
    if (s == "Committed" || s == "Invalid") {
      break;
    }
  }
  check_committed(s);
}

// perform a single put request but poll until it is committed
export function put_single_wait() {
  const txid = put_single();
  wait_for_committed(txid);
}

// perform a single get request at a preset key
export function get_single() {
  let payload = JSON.stringify({
    key: key0,
  });

  let response = http.post("${host}/v3/kv/range", payload, json_header_params);

  check_success(response);
}

// perform a single delete request at a preset key
export function delete_single() {
  let payload = JSON.stringify({
    key: key0,
  });

  let response = http.post(
    `${host}/v3/kv/delete_range`,
    payload,
    json_header_params
  );

  check_success(response);
}

// perform a single delete request but poll until it is committed
export function delete_single_wait() {
  const txid = delete_single();
  wait_for_committed(txid);
}

// Randomly select a request type to run
export function mixed_single() {
  const rnd = Math.random();
  if (rnd >= 0 && rnd < 0.6) {
    // 60% reads
    get_single();
  } else if (rnd >= 0.5 && rnd < 0.85) {
    // 35% writes
    put_single();
  } else if (rnd >= 0.85 && rnd < 0.9) {
    // 5% writes
    put_single_wait();
  } else if (rnd >= 0.9 && rnd < 0.98) {
    // 8% deletes
    delete_single();
  } else {
    // 2% deletes
    delete_single_wait();
  }
}

export function get_receipt(receipt_txids) {
  const txid =
    receipt_txids[exec.scenario.iterationInTest % receipt_txids.length];

  const [revision, raftTerm] = txid.split(".");
  let payload = JSON.stringify({
    revision: revision,
    raftTerm: raftTerm,
  });

  const response = http.post(
    `${host}/v3/receipt/get_receipt`,
    payload,
    json_header_params
  );
  check_success(response);
}
