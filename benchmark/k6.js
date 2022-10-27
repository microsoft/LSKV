import { check } from "k6";
import http from "k6/http";

export let options = {
  vus: 1,
  duration: "10s",
  tlsAuth: [
    {
      cert: open("../certs/client.pem"),
      key: open("../certs/client-key.pem"),
    },
  ],
  insecureSkipTLSVerify: true,
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
    "status is 200": (r) => r.status === 200,
  });
}
