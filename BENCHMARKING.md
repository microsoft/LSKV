# Benchmarking the KVS

With the implementation of the etcd API we can use the [etcd benchmark tool](https://github.com/etcd-io/etcd/tree/main/tools/benchmark) to run benchmarks quite easily.

## Running

### Dependencies

1. Submodules need to be initialised (`git submodule update --init`)
2. [Golang](https://go.dev/doc/install) needs to be installed.

```sh
make benchmark
```
