# Benchmarking the KVS

With the implementation of the etcd API we can use the [etcd benchmark tool](https://github.com/etcd-io/etcd/tree/main/tools/benchmark) to run benchmarks quite easily.

## Running

```sh
make run-virtual

# in another terminal
./benchmark.sh put
# or
./benchmark.sh range
./benchmark.sh txn-put
```

## Issues

Currently the etcd benchmark program only gives us a summary of the results, we should patch it to provide us with all of the result data so that we can plot it ourselves.
