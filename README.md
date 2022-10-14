# LSKV

[![Open in VSCode](https://img.shields.io/static/v1?label=Open+in&message=VSCode&logo=visualstudiocode&color=007ACC&logoColor=007ACC&labelColor=2C2C32)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/microsoft/LSKV) [![LSKV CI](https://github.com/microsoft/LSKV/actions/workflows/ci.yml/badge.svg)](https://github.com/microsoft/LSKV/actions/workflows/ci.yml)

The Ledger-backed Secure Key-Value store, also known as LSKV, is a research project to investigate whether it is possible to build a trustworthy distributed data store on top of the [Confidential Consortium Framework (CCF)](https://github.com/microsoft/CCF). LSKV aims to provide gRPC & HTTP/JSON APIs, similar to that of existing key-value stores such as [etcd](https://etcd.io/), with support for common operations such as watches and leases, whilst taking advantage of the confidentiality guarantees, auditability, and multi-party governance provided by CCF.

**This early stage research prototype should not be used in production.**

## Install Dependencies

This repository and its dependencies can be checked out by clicking: [![Open in VSCode](https://img.shields.io/static/v1?label=Open+in&message=VSCode&logo=visualstudiocode&color=007ACC&logoColor=007ACC&labelColor=2C2C32)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/microsoft/LSKV)

Alternatively, CCF and its dependencies can be installed manually:

```bash
make install-ccf
```

Or

```bash
$ wget https://github.com/microsoft/CCF/releases/download/ccf-3.0.0-dev5/ccf_3.0.0_dev5_amd64.deb
$ sudo dpkg -i ccf_3.0.0_dev5_amd64.deb # Installs CCF under /opt/ccf
$ cat /opt/ccf/share/VERSION_LONG
ccf-3.0.0-dev5
$ /opt/ccf/getting_started/setup_vm/run.sh /opt/ccf/getting_started/setup_vm/app-dev.yml  # Install dependencies
```

If your organisation supports it, you can also checkout this repository in a Github codespace: [![Open in Github codespace](https://img.shields.io/static/v1?label=Open+in&message=GitHub+codespace&logo=github&color=2F363D&logoColor=white&labelColor=2C2C32)](https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=534240617&machine=basicLinux32gb&devcontainer_path=.devcontainer.json&location=WestEurope)

## Build

In the local checkout of this repository:

### Virtual (non-attested)

```bash
make build-virtual
```

Builds `build/liblskv.virtual.so`.

#### Docker

Alternatively, it is possible to build a runtime image of this application via docker:

```bash
$ docker build -t lskv-virtual -f Dockerfile.virtual .
```

### SGX (attested)

```bash
make build-sgx
```

Builds `build/liblskv.enclave.so.signed`.

#### Docker

Alternatively, it is possible to build a runtime image of this application via docker:

```bash
$ docker build -t lskv-sgx -f Dockerfile.sgx .
```

## Testing

### Etcd integration tests

To run some etcd integration tests:

```sh
make test-virtual
```

## Run

### Locally

```bash
$ make run-virtual
```

Or

```bash
$ /opt/ccf/bin/sandbox.sh -p ./liblskv.virtual.so --http2
```

Producing:

```sh
Setting up Python environment...
Python environment successfully setup
[12:00:00.000] Virtual mode enabled
[12:00:00.000] Starting 1 CCF node...
[12:00:00.000] Started CCF network with the following nodes:
[12:00:00.000]   Node [0] = https://127.0.0.1:8000
[12:00:00.000] You can now issue business transactions to the ./liblskv.virtual.so application
[12:00:00.000] Keys and certificates have been copied to the common folder: .../LSKV/build/workspace/sandbox_common
[12:00:00.000] See https://microsoft.github.io/CCF/main/use_apps/issue_commands.html for more information
[12:00:00.000] Press Ctrl+C to shutdown the network
```

Or, for an SGX-enabled application: `$ make run-sgx` or `$ /opt/ccf/bin/sandbox.sh -p ./liblskv.enclave.so.signed -e release --http2`.

### With docker in Virtual mode

```bash
$ docker run --name lskv -it --rm lskv-virtual
...
2022-01-01T12:00:00.000000Z -0.000 0   [info ] ../src/node/node_state.h:1790        | Network TLS connections now accepted
# It is then possible to interact with the service
```

### With docker in SGX mode

```bash
$ docker run --name lskv -it --rm --device /dev/sgx_enclave:/dev/sgx_enclave --device /dev/sgx_provision:/dev/sgx_provision -v /dev/sgx:/dev/sgx lskv-sgx
...
2022-01-01T12:00:00.000000Z -0.000 0   [info ] ../src/node/node_state.h:1790        | Network TLS connections now accepted
# It is then possible to interact with the service
```

## Interacting with the store

**Note**: When running with Docker extra setup steps are currently required before interacting with the store as below, see [Running a CCF Service](https://microsoft.github.io/CCF/main/operations/start_network.html#opening-a-network-to-users).

### etcdctl (gRPC API)

You can use the official etcd CLI client for interacting with the datastore over gRPC, for supported methods see the [gRPC API status](https://github.com/microsoft/LSKV/issues/35).

```bash
$ ./etcdctl.sh put key value
OK

$ ./etcdctl.sh get key
key
value
```

### JSON API

We also allow calling with the [JSON API](https://etcd.io/docs/v3.5/dev-guide/api_grpc_gateway/).
The status of the JSON API follows that of the [gRPC API](https://github.com/microsoft/LSKV/issues/35).

To call an endpoint with curl:

```sh
# read an empty value from 'hello'
curl -X POST https://127.0.0.1:8000/v3/kv/range --cacert workspace/sandbox_common/service_cert.pem --key workspace/sandbox_common/user0_privk.pem --cert workspace/sandbox_common/user0_cert.pem  -H "content-type: application/json" -i --data-binary '{"key":"aGVsbG8="}'

# put a value 'world' at 'hello'
curl -X POST https://127.0.0.1:8000/v3/kv/put --cacert workspace/sandbox_common/service_cert.pem --key workspace/sandbox_common/user0_privk.pem --cert workspace/sandbox_common/user0_cert.pem  -H "content-type: application/json" -i --data-binary '{"key":"aGVsbG8=","value":"d29ybGQ="}'

# read the put value at 'hello'
curl -X POST https://127.0.0.1:8000/v3/kv/range --cacert workspace/sandbox_common/service_cert.pem --key workspace/sandbox_common/user0_privk.pem --cert workspace/sandbox_common/user0_cert.pem  -H "content-type: application/json" -i --data-binary '{"key":"aGVsbG8="}'

# delete the put value at 'hello'
curl -X POST https://127.0.0.1:8000/v3/kv/delete_range --cacert workspace/sandbox_common/service_cert.pem --key workspace/sandbox_common/user0_privk.pem --cert workspace/sandbox_common/user0_cert.pem  -H "content-type: application/json" -i --data-binary '{"key":"aGVsbG8="}'
```

## Benchmarking

See [BENCHMARKING.md](./BENCHMARKING.md) for instructions to run the benchmarks and analysis.
