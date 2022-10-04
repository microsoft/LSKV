# Ledger-backed Secure Key-Value Store (LSKV)

[![LSKV CI](https://github.com/microsoft/LSKV/actions/workflows/ci.yml/badge.svg)](https://github.com/microsoft/LSKV/actions/workflows/ci.yml)

Ledger-backed Secure Key-Value Stored app sample based on [CCF](https://github.com/microsoft/ccf).

## Install Dependencies

Install CCF and its dependencies:

```bash
$ wget https://github.com/microsoft/CCF/releases/download/ccf-3.0.0-dev3/ccf_3.0.0_dev3_amd64.deb
$ sudo dpkg -i ccf_3.0.0_dev3_amd64.deb # Install CCF under /opt/ccf
$ cat /opt/ccf/share/VERSION_LONG
ccf-3.0.0-dev3
$ /opt/ccf/getting_started/setup_vm/run.sh /opt/ccf/getting_started/setup_vm/app-dev.yml  # Install dependencies
```

Alternatively, you can checkout this repository in a [VSCode development container](https://code.visualstudio.com/docs/remote/containers).

## Build

In the local checkout of this repository:

```bash
$ cd LSKV
$ mkdir build
$ cd build
# to build with public maps (more debuggable) add -DPUBLIC_MAPS
$ CC="/opt/oe_lvi/clang-10" CXX="/opt/oe_lvi/clang++-10" cmake -GNinja ..
$ ninja
$ ls
libccf_kvs.enclave.so.signed # SGX-enabled application
libccf_kvs.virtual.so # Virtual application (i.e. insecure!)
```

## Test

### Manual

```bash
$ /opt/ccf/bin/sandbox.sh -p ./libccf_kvs.virtual.so
Setting up Python environment...
Python environment successfully setup
[12:00:00.000] Virtual mode enabled
[12:00:00.000] Starting 1 CCF node...
[12:00:00.000] Started CCF network with the following nodes:
[12:00:00.000]   Node [0] = https://127.0.0.1:8000
[12:00:00.000] You can now issue business transactions to the ./libccf_kvs.virtual.so application
[12:00:00.000] Keys and certificates have been copied to the common folder: .../LSKV/build/workspace/sandbox_common
[12:00:00.000] See https://microsoft.github.io/CCF/main/use_apps/issue_commands.html for more information
[12:00:00.000] Press Ctrl+C to shutdown the network
```

Or, for an SGX-enabled application: `$ /opt/ccf/bin/sandbox.sh -p ./libccf_kvs.enclave.so.signed -e release`

### Etcd integration

To run some etcd integration tests:

```sh
make test-virtual
```

## Docker

Alternatively, it is possible to build a runtime image of this application via docker:

```bash
$ docker build -t lskv .
$ docker run --device /dev/sgx_enclave:/dev/sgx_enclave --device /dev/sgx_provision:/dev/sgx_provision -v /dev/sgx:/dev/sgx lskv
...
2022-01-01T12:00:00.000000Z -0.000 0   [info ] ../src/node/node_state.h:1790        | Network TLS connections now accepted
# It is then possible to interact with the service
```

## etcd

```bash
# run the datastore from the project root
$ /opt/ccf/bin/sandbox.sh -p build/libccf_kvs.virtual.so --http2
...

# In another terminal, from the project root
$ ./etcdctl.sh put key value
OK

$ ./etcdctl.sh get key
key
value
```

### JSON API

We also allow calling with the [JSON API](https://etcd.io/docs/v3.5/dev-guide/api_grpc_gateway/) for some endpoints.
See [the status of the JSON API](https://github.com/microsoft/LSKV/issues/50) for which endpoints have JSON API implementations.

To call an endpoint with curl:

```sh
# start the datastore
make run-virtual

# read an empty value from 'hello'
curl -X POST https://127.0.0.1:8000/v3/kv/range --cacert workspace/sandbox_common/service_cert.pem --key workspace/sandbox_common/user0_privk.pem --cert workspace/sandbox_common/user0_cert.pem  -H "content-type: application/json" -i --data-binary '{"key":"aGVsbG8="}'

# put a value 'world' at 'hello'
curl -X POST https://127.0.0.1:8000/v3/kv/put --cacert workspace/sandbox_common/service_cert.pem --key workspace/sandbox_common/user0_privk.pem --cert workspace/sandbox_common/user0_cert.pem  -H "content-type: application/json" -i --data-binary '{"key":"aGVsbG8=","value":"d29ybGQ="}'

# read the put value at 'hello'
curl -X POST https://127.0.0.1:8000/v3/kv/range --cacert workspace/sandbox_common/service_cert.pem --key workspace/sandbox_common/user0_privk.pem --cert workspace/sandbox_common/user0_cert.pem  -H "content-type: application/json" -i --data-binary '{"key":"aGVsbG8="}'

# delete the put value at 'hello'
curl -X POST https://127.0.0.1:8000/v3/kv/delete_range --cacert workspace/sandbox_common/service_cert.pem --key workspace/sandbox_common/user0_privk.pem --cert workspace/sandbox_common/user0_cert.pem  -H "content-type: application/json" -i --data-binary '{"key":"aGVsbG8="}'
```
