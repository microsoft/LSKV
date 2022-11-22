// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.
import { check, randomSeed } from "k6";
import http from "k6/http";
import encoding from "k6/encoding";
import exec from "k6/execution";
import grpc from "k6/net/grpc";

const rate = Number(__ENV.RATE);
const workspace = __ENV.WORKSPACE;
const preAllocatedVUs = __ENV.PRE_ALLOCATED_VUS;
const maxVUs = __ENV.MAX_VUS;
const func = __ENV.FUNC;
const content_type = __ENV.CONTENT_TYPE;

const duration_s = 10;

const grpc_client = new grpc.Client();
grpc_client.load(["definitions"], "../../proto/etcd.proto");

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

function key(i) {
  return encoding.b64encode(`key${i}`);
}
const val0 = encoding.b64encode("value0");

const addr = "127.0.0.1:8000";
const host = `https://${addr}`;

const total_requests = rate * duration_s;
const prefill_keys = total_requests / 2;

export function setup() {
  randomSeed(123);

  if (content_type == "grpc") {
    grpc_client.connect(addr, {});
  }

  let receipt_txids = [];
  var txid = "";
  // trigger getting some cached ones too (maybe)
  for (let i = 0; i < prefill_keys; i++) {
    // issue some writes so we have things to get receipts for
    txid = put_single(i, "setup");
    receipt_txids.push(txid);
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
export function put_single(i = 0, tag = "put_single") {
  if (content_type == "grpc") {
    if (tag != "setup" && exec.vu.iterationInInstance == 0) {
      grpc_client.connect(addr, {});
    }
    const payload = {
      key: key(i),
      value: val0,
    };
    const response = grpc_client.invoke("etcdserverpb.KV/Put", payload);

    check(response, {
      "status is 200": (r) => r && r.status === grpc.StatusOK,
    });

    const res = response.message;
    const header = res["header"];
    const term = header["raftTerm"];
    const rev = header["revision"];
    const txid = `${term}.${rev}`;
    return txid;
  } else {
    let payload = JSON.stringify({
      key: key(i),
      value: val0,
    });
    let params = {
      headers: {
        "Content-Type": "application/json",
      },
      tags: {
        caller: tag,
      },
    };

    let response = http.post(`${host}/v3/kv/put`, payload, params);

    check_success(response);

    const res = response.json();
    const header = res["header"];
    const term = header["raftTerm"];
    const rev = header["revision"];
    const txid = `${term}.${rev}`;
    return txid;
  }
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
export function put_single_wait(i = 0) {
  const txid = put_single(i, "put_single_wait");
  wait_for_committed(txid);
}

// perform a single get request at a preset key
export function get_single(i = 0, tag = "get_single") {
  if (content_type == "grpc") {
    if (tag != "setup" && exec.vu.iterationInInstance == 0) {
      grpc_client.connect(addr, {});
    }
    const payload = {
      key: key(i),
    };
    const response = grpc_client.invoke("etcdserverpb.KV/Range", payload);

    check(response, {
      "status is 200": (r) => r && r.status === grpc.StatusOK,
    });
  } else {
    let payload = JSON.stringify({
      key: key(i),
    });
    let params = {
      headers: {
        "Content-Type": "application/json",
      },
      tags: {
        caller: tag,
      },
    };

    let response = http.post(`${host}/v3/kv/range`, payload, params);

    check_success(response);
  }
}

// perform a single get request at a preset key
export function get_range(i = 0, tag = "get_range") {
  let payload = JSON.stringify({
    key: key(i),
    range_end: key(i + 1000),
  });
  let params = {
    headers: {
      "Content-Type": "application/json",
    },
    tags: {
      caller: tag,
    },
  };

  let response = http.post(`${host}/v3/kv/range`, payload, params);

  check_success(response);
}

// perform a single delete request at a preset key
export function delete_single(i = 0, tag = "delete_single") {
  if (content_type == "grpc") {
    if (tag != "setup" && exec.vu.iterationInInstance == 0) {
      grpc_client.connect(addr, {});
    }
    const payload = {
      key: key(i),
    };
    const response = grpc_client.invoke("etcdserverpb.KV/DeleteRange", payload);

    check(response, {
      "status is 200": (r) => r && r.status === grpc.StatusOK,
    });
  } else {
    let payload = JSON.stringify({
      key: key(i),
    });
    let params = {
      headers: {
        "Content-Type": "application/json",
      },
      tags: {
        caller: tag,
      },
    };

    let response = http.post(`${host}/v3/kv/delete_range`, payload, params);

    check_success(response);
  }
}

export function put_get_delete(i = 0) {
  put_single(i);
  get_single(i);
  delete_single(i);
}

// perform a single delete request but poll until it is committed
export function delete_single_wait(i = 0) {
  const txid = delete_single(i, "delete_single_wait");
  wait_for_committed(txid);
}

// Randomly select a request type to run
export function mixed_single() {
  const rnd = Math.random();
  if (rnd >= 0 && rnd < 0.6) {
    // 60% reads
    get_single();
  } else if (rnd >= 0.6 && rnd < 0.9) {
    // 30% writes
    put_single();
  } else {
    // 10% deletes
    delete_single();
  }
}

// Randomly select a request type to run
export function mixed_single_wait() {
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

export function get_receipt(receipt_txids, tag = "get_receipt") {
  const txid =
    receipt_txids[exec.scenario.iterationInTest % receipt_txids.length];

  const [revision, raftTerm] = txid.split(".");
  let payload = JSON.stringify({
    revision: revision,
    raftTerm: raftTerm,
  });
  let params = {
    headers: {
      "Content-Type": "application/json",
    },
    tags: {
      caller: tag,
    },
  };

  const response = http.post(`${host}/v3/receipt/get_receipt`, payload, params);
  check_success(response);
}
