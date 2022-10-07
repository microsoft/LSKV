# Benchmarking LSKV

With the implementation of the etcd API benchmark runs can use the [etcd benchmark tool](https://github.com/etcd-io/etcd/tree/main/tools/benchmark) quite easily.

## Running

### Dependencies

1. Submodules need to be initialised (`git submodule update --init`)
2. [Golang](https://go.dev/doc/install) needs to be installed.

```sh
make benchmark-virtual
```

Or with the SGX benchmarks:

```sh
make benchmark-sgx
```

## Analysing

The analysis is currently available as a jupyter notebook.

Either run it interactively:

```sh
make notebook
```

Or just run it single-shot

```sh
make execute-notebook
```

The plots should be saved in the `plots` directory.