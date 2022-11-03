import { check } from "k6";
import http from "k6/http";

export let options = {
  tlsAuth: [
    {
      cert: open("../certs/client.pem"),
      key: open("../certs/client-key.pem"),
    },
  ],
  insecureSkipTLSVerify: true,
  duration: '10s',
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
