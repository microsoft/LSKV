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

## Distributed benchmarking

### Requirements

The distributed benchmarking assumes a set of machines are available (running Ubuntu 20.04).
Their IP addresses should be available in a `hosts` file one per line.
The first node listed in this file will be the _leader_ node and be responsible for launching the benchmarks from.

If using a VM scale set in Azure, running the following will get the IP addreses into the hosts file for you if they have public IP addresses:

```sh
az vmss list-instance-public-ips --name <vmss_name> --resource-group <vmss_rg> | jq -r '.[].ipAddress' | tee hosts
```

For VMs with private IP addresses reachable from a jumpbox you'll be running the commands from:

```sh
az vmss nic list --vmss-name <vmss_name> --resource-group <vmss_rg> | jq -r '.[].ipConfigurations[].privateIpAddress' | tee hosts
```

After provisioning the nodes, they need to be setup with the correct dependencies:

```sh
ansible-playbook -i hosts benchmark/distributed/setup_nodes.yaml -e @benchmark/distributed/values.yaml
```

Then, to run the benchmarks, ssh onto the first node (`ssh <user>@$(head -n 1 hosts)`), `cd /tmp/lskv` and run things from there (e.g. `. .venv/bin/activate && python3 benchmark/distributed.py`).
