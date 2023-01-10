// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.
import { check, randomSeed, sleep } from "k6";
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
const addr = __ENV.ADDR;
const valueSize = __ENV.VALUE_SIZE;

const duration_s = 5;
const stageCount = 5;

function getStages() {
  // start with a warm up
  let stages = [{ target: 100, duration: "1s" }];
  // ramp up
  for (let i = 0; i < stageCount; i++) {
    const target = Math.floor(rate * ((i + 1) / stageCount));
    // initial quick ramp up
    stages.push({ target: target, duration: `1s` });
    // followed by steady state for a bit
    stages.push({ target: target, duration: `${duration_s}s` });
  }
  // ramp down
  for (let i = stageCount - 1; i >= 0; i--) {
    const target = Math.floor(rate * ((i + 1) / stageCount));
    // initial quick ramp down
    stages.push({ target: target, duration: `1s` });
    // followed by steady state for a bit
    stages.push({ target: target, duration: `${duration_s}s` });
  }
  // end with a cool-down
  stages.push({ target: 100, duration: "1s" });
  return stages;
}

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
      executor: "ramping-arrival-rate",
      exec: func,
      startRate: 100,
      timeUnit: "1s",
      preAllocatedVUs: preAllocatedVUs,
      maxVUs: maxVUs,
      stages: getStages(),
    },
  },
};

function key(i) {
  return encoding.b64encode(`key${i}`);
}
const val0 = encoding.b64encode("v".repeat(valueSize));

const host = `https://${addr}`;

export function setup() {
  randomSeed(123);

  if (content_type == "grpc") {
    grpc_client.connect(addr, {});
  }
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

    const req_resp = {
      method: "put",
      req: payload,
      res: res,
      time: Date.now(),
    };
    console.log(JSON.stringify(req_resp));

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

    const req_resp = {
      method: "put",
      req: payload,
      res: res,
      time: Date.now(),
    };
    console.log(JSON.stringify(req_resp));
    return txid;
  }
}

// check the status of a transaction id with the service
function get_tx_status(txid) {
  const response = http.get(`${host}/app/tx?transaction_id=${txid}`);
  const res = response.json()
  const req_resp = {
    method: "get_tx_status",
    req: txid,
    res: res,
    time:Date.now(),
  }
  console.log(JSON.stringify(req_resp))
  return res["status"];
}

function wait_for_committed(txid) {
  var s = "";
  const tries = 1000;
  for (let i = 0; i < tries; i++) {
    s = get_tx_status(txid);
    if (s == "Committed" || s == "Invalid") {
      break;
    }
    // sleep for 100ms to give the node a chance to commit things
    sleep(0.01);
  }
  check_committed(s);
}

// perform a single put request but poll until it is committed
export function put_single_wait(i = 0) {
  const txid = put_single(i, "put_single_wait");
  wait_for_committed(txid);
  return txid;
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

    const req_resp = {
      method: "get",
      req: payload,
      res: response.message,
      time: Date.now(),
    };
    console.log(JSON.stringify(req_resp));
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
    const req_resp = {
      method: "get",
      req: payload,
      res: response.json(),
      time: Date.now(),
    };
    console.log(JSON.stringify(req_resp));
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

    const res = response.message;
    const header = res["header"];
    const term = header["raftTerm"];
    const rev = header["revision"];
    const txid = `${term}.${rev}`;

    const req_resp = {
      method: "delete",
      req: payload,
      res: response.message,
      time: Date.now(),
    };
    console.log(JSON.stringify(req_resp));

    return txid;
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

    const res = response.json();
    const header = res["header"];
    const term = header["raftTerm"];
    const rev = header["revision"];
    const txid = `${term}.${rev}`;

    check_success(response);
    const req_resp = {
      method: "delete",
      req: payload,
      res: res,
      time: Date.now(),
    };
    console.log(JSON.stringify(req_resp));

    return txid;
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
  return txid;
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

// Randomly select a request type to run
export function mixed_single_receipt() {
  const rnd = Math.random();
  if (rnd >= 0 && rnd < 0.6) {
    // 60% reads
    get_single();
  } else if (rnd >= 0.6 && rnd < 0.9) {
    // 30% writes
    const txid = put_single_wait();
    get_receipt(txid);
  } else {
    // 10% deletes
    const txid = delete_single_wait();
    get_receipt(txid);
  }
}

export function get_receipt(txid, tag = "get_receipt") {
  const [raftTerm, revision] = txid.split(".");
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

  var response = http.post(`${host}/v3/receipt/get_receipt`, payload, params);
  check_success(response);
  while (response.status == 202){
    // sleep for 10ms to give the node a chance to process the receipt
    sleep(0.01);
    // try again
    response = http.post(`${host}/v3/receipt/get_receipt`, payload, params);
    check_success(response);
  }

  const req_resp = {
    method: "receipt",
    req: payload,
    res: response.json(),
      time: Date.now(),
  };
  console.log(JSON.stringify(req_resp));
}
