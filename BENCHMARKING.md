# Benchmarking LSKV

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

## Receipt verification

The receipt verification benchmark (`benchmark/receipt_verify.py`) uses a hard-coded receipt so can be run standalone without a running datastore.
It can be run with `PYTHONPATH=tests python benchmark/receipt_verify.py`.