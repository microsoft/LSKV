// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.
import { check } from "k6";
import http from "k6/http";

const rate = Number(__ENV.RATE);
const workspace = __ENV.WORKSPACE;
const preAllocatedVUs = __ENV.PRE_ALLOCATED_VUS;
const maxVUs = __ENV.MAX_VUS;

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
      rate: rate,
      duration: "10s",
      timeUnit: "1s",
      preAllocatedVUs: preAllocatedVUs,
      maxVUs: maxVUs,
    },
  },
};

export default function () {
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
}
