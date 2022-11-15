#!/usr/bin/env python3

import argparse
import subprocess
from typing import List

from loguru import logger


def run(cmd:str) :
    logger.info(f"Run: {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def get_hosts(filename:str) ->List[str]:
    with open(filename, "r", encoding="utf-8") as file:
        hosts = [f.strip() for f in file.readlines()]
        return hosts

def get_args()->argparse.Namespace:
    parser= argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True, help="how many nodes to make for the benchmark")
    parser.add_argument("--resource-group", type=str,  required=True,help="resource group for the scale set")
    parser.add_argument("--vmss-name", type=str,  required=True,help="name for the vm scale set")
    parser.add_argument("--hosts-file", type=str,  required=True,help="file to store hosts in")
    parser.add_argument("--ssh-key-file", type=str,  required=True,help="file to store the main benchmark nodes public ssh key in")
    parser.add_argument("--user", type=str,  required=True,help="username for the vms")
    return parser.parse_args()

def main():
    args = get_args()

    run(f"az vmss scale --name {args.vmss_name} --resource-group {args.resource_group} --new-capacity {args.count}")
    run(f"az vmss list-instance-public-ips --name {args.vmss_name} --resource-group {args.resource_group} | jq -r '.[].ipAddress' | tee {args.hosts_file}")

    hosts = get_hosts(args.hosts_file)
    run(f"rsync -rv --filter='dir-merge,- .gitignore' --exclude='/.git' {args.user}@{hosts[0]}:/tmp/lskv")

    # get the key for the first node
    run(f"ssh {args.user}@{hosts[0]} \"ssh-keygen -t rsa -N '' -f /home/{args.user}/.ssh/id_rsa <<< y\"")

    run(f"rsync {args.user}@{hosts[0]}:/home/{args.user}/.ssh/id_rsa.pub {args.ssh_key_file}")

    bench_ssh_key = open(args.ssh_key_file, "r", encoding="utf-8").read()

    for host in hosts:
        run(f"ssh-keyscan {host} >> ~/.ssh/known_hosts")
        run(f"ssh {args.user}@{host} \"echo '{bench_ssh_key}' >> /home/{args.user}/.ssh/authorized_keys\"")

if __name__ == "__main__":
    main()
