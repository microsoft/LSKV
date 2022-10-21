#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run ci pull_request configurations of the benchmarks
"""

import argparse
import logging
from typing import List

import common
import etcd
import ycsb

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.DEBUG)


def etcd_configurations(args: argparse.Namespace) -> List[etcd.EtcdConfig]:
    """
    Set args for all etcd configurations.
    """
    args.bench_args = [["put"]]
    args.clients = [10]
    args.connections = [10]
    args.rate = [1000]

    args.worker_threads = [0]
    args.virtual = True
    args.sgx = True

    return etcd.make_configurations(args)


def ycsb_configurations(args: argparse.Namespace) -> List[ycsb.YCSBConfig]:
    """
    Set args for all ycsb configurations.
    """
    args.workloads = ["a"]
    args.rate = [1000]
    args.threads = [1]

    args.worker_threads = [0]
    args.virtual = True
    args.sgx = True

    return ycsb.make_configurations(args)


if __name__ == "__main__":
    common.main("etcd", etcd.get_arguments, etcd_configurations, etcd.execute_config)
    common.main("ycsb", ycsb.get_arguments, ycsb_configurations, ycsb.execute_config)
