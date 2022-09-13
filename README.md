# CCF Key-Value Store Sample App

[![CCF KVS CI](https://github.com/microsoft/ccf-kvs/actions/workflows/ci.yml/badge.svg)](https://github.com/microsoft/ccf-kvs/actions/workflows/ci.yml)

CCF sample application of a key-value store.

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
$ cd ccf-kvs
$ mkdir build
$ cd build
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
[12:00:00.000] Keys and certificates have been copied to the common folder: .../ccf-kvs/build/workspace/sandbox_common
[12:00:00.000] See https://microsoft.github.io/CCF/main/use_apps/issue_commands.html for more information
[12:00:00.000] Press Ctrl+C to shutdown the network
```

Or, for an SGX-enabled application: `$ /opt/ccf/bin/sandbox.sh -p ./libccf_kvs.enclave.so.signed -e release`

### Etcd integration

To run some etcd integration tests:

```sh
3rdparty/etcd/tests/ccf-kvs.sh
```

## Docker

Alternatively, it is possible to build a runtime image of this application via docker:

```bash
$ docker build -t ccf-kvs .
$ docker run --device /dev/sgx_enclave:/dev/sgx_enclave --device /dev/sgx_provision:/dev/sgx_provision -v /dev/sgx:/dev/sgx ccf-kvs
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
