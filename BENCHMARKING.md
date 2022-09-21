# Benchmarking the KVS

With the implementation of the etcd API we can use the [etcd benchmark tool](https://github.com/etcd-io/etcd/tree/main/tools/benchmark) to run benchmarks quite easily.

## Running

```sh
./benchmark.py
```

## Issues

Currently the etcd benchmark program only gives us a summary of the results, we should patch it to provide us with all of the result data so that we can plot it ourselves.

The etcd benchmarking program also forces using the progress reporter which clogs up the output unfortunately.
