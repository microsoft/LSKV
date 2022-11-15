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

def setup_node(user:str,ip:str):
    run(f"ssh {user}@{ip} \"sudo apt update && sudo apt install make python3.8 python3.8-venv && cd /tmp/lskv && make install-ccf-virtual .venv\"")


def wait_for_ssh(user:str,ip:str, tries=60):
    for _ in range(tries):
        try:
            run(f"ssh-keyscan {ip}")
            logger.info("ssh is ready")
            break
        except:
            continue


def main():
    args = get_args()

    run(f"az vmss scale --name {args.vmss_name} --resource-group {args.resource_group} --new-capacity {args.count}")
    run(f"az vmss list-instance-public-ips --name {args.vmss_name} --resource-group {args.resource_group} | jq -r '.[].ipAddress' | tee {args.hosts_file}")

    hosts = get_hosts(args.hosts_file)

    for host in hosts:
        wait_for_ssh(args.user,host)
        run(f"ssh-keyscan {host} >> ~/.ssh/known_hosts")


    # get the key for the first node
    run(f"ssh {args.user}@{hosts[0]} \"ssh-keygen -t rsa -N '' -f /home/{args.user}/.ssh/id_rsa <<< y\"")

    run(f"rsync {args.user}@{hosts[0]}:/home/{args.user}/.ssh/id_rsa.pub {args.ssh_key_file}")

    bench_ssh_key = open(args.ssh_key_file, "r", encoding="utf-8").read()

    for host in hosts:
        # allow leader node to ssh to this node
        run(f"ssh {args.user}@{host} \"echo '{bench_ssh_key}' >> /home/{args.user}/.ssh/authorized_keys\"")

        run(f"rsync -rv --exclude='/.git' --exclude=bench --include=build . {args.user}@{host}:/tmp/lskv")
        setup_node(args.user, host)

if __name__ == "__main__":
    main()
