// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.
import { check, randomSeed } from "k6";
import http from "k6/http";

const rate = Number(__ENV.RATE);
const workspace = __ENV.WORKSPACE;
const preAllocatedVUs = __ENV.PRE_ALLOCATED_VUS;
const maxVUs = __ENV.MAX_VUS;
const func = __ENV.FUNC;

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
      duration: "10s",
      timeUnit: "1s",
      preAllocatedVUs: preAllocatedVUs,
      maxVUs: maxVUs,
    },
  },
};

export function setup() {
  // write a key to the store for get clients
  put_single_wait();
  randomSeed(123);
}

// perform a single put request at a preset key
export function put_single() {
  let payload = JSON.stringify({
    key: "a2V5Cg==",
    value: "dmFsCg==",
  });

  let params = {
    headers: {
      "Content-Type": "application/json",
    },
  };

  let response = http.post("https://127.0.0.1:8000/v3/kv/put", payload, params);

  check(response, {
    "http1 is used": (r) => r.proto === "HTTP/1.1",
    "status is 200": (r) => r.status === 200,
  });

  const res = response.json();
  const header = res["header"];
  const term = header["raftTerm"];
  const rev = header["revision"];
  const txid = `${term}.${rev}`;
  return txid;
}

// check the status of a transaction id with the service
function get_tx_status(txid) {
  const response = http.get(
    `https://127.0.0.1:8000/app/tx?transaction_id=${txid}`
  );
  return response.json()["status"];
}

// perform a single put request but poll until it is committed
export function put_single_wait() {
  const txid = put_single();

  var s = "";
  const tries = 1000;
  for (let i = 0; i < tries; i++) {
    s = get_tx_status(txid);
    if (s == "Committed" || s == "Invalid") {
      console.log(`${s} in ${i}`);
      break;
    }
  }

  check(s, {
    "committed within limit": (s) => s === "Committed",
  });
}

// perform a single get request at a preset key
export function get_single() {
  let payload = JSON.stringify({
    key: "a2V5Cg==",
  });

  let params = {
    headers: {
      "Content-Type": "application/json",
    },
  };

  let response = http.post(
    "https://127.0.0.1:8000/v3/kv/range",
    payload,
    params
  );

  check(response, {
    "http1 is used": (r) => r.proto === "HTTP/1.1",
    "status is 200": (r) => r.status === 200,
  });
}

// perform a single delete request at a preset key
export function delete_single() {
  let payload = JSON.stringify({
    key: "a2V5Cg==",
  });

  let params = {
    headers: {
      "Content-Type": "application/json",
    },
  };

  let response = http.post(
    "https://127.0.0.1:8000/v3/kv/delete_range",
    payload,
    params
  );

  check(response, {
    "http1 is used": (r) => r.proto === "HTTP/1.1",
    "status is 200": (r) => r.status === 200,
  });
}

// perform a single delete request but poll until it is committed
export function delete_single_wait() {
  const txid = delete_single();

  var s = "";
  const tries = 1000;
  for (let i = 0; i < tries; i++) {
    s = get_tx_status(txid);
    if (s == "Committed" || s == "Invalid") {
      console.log(`${s} in ${i}`);
      break;
    }
  }

  check(s, {
    "committed within limit": (s) => s === "Committed",
  });
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
