#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run ci pull_request configurations of the benchmarks
"""

import argparse
from typing import List

# pylint: disable=duplicate-code
import common
import etcd
import k6
import perf_system as perf
import ycsb


def common_configurations(args: argparse.Namespace):
    """
    Fill in the args for all common configurations.
    """
    args.worker_threads = [0]
    args.virtual = True
    args.etcd = True
    args.sgx = False
    args.http2 = True
    args.nodes = [1]


def etcd_configurations(args: argparse.Namespace) -> List[etcd.EtcdConfig]:
    """
    Set args for all etcd configurations.
    """
    args.bench_args = [["put"]]
    args.clients = [10]
    args.connections = [10]
    args.rate = [1000]

    common_configurations(args)

    return etcd.make_configurations(args)


def ycsb_configurations(args: argparse.Namespace) -> List[ycsb.YCSBConfig]:
    """
    Set args for all ycsb configurations.
    """
    args.workloads = ["a"]
    args.rate = [1000]
    args.threads = [1]

    common_configurations(args)

    return ycsb.make_configurations(args)


def perf_configurations(args: argparse.Namespace) -> List[perf.PerfConfig]:
    """
    Set args for all perf configurations.
    """
    common_configurations(args)
    args.http1 = True

    return perf.make_configurations(args)


def k6_configurations(args: argparse.Namespace) -> List[k6.K6Config]:
    """
    Set args for all k6 configurations.
    """
    common_configurations(args)
    args.http1 = True
    args.http2 = True
    args.etcd = False
    args.func = [
        "put_single",
        "put_single_wait",
        "get_single",
        "get_range",
        "delete_single",
        "delete_single_wait",
        "mixed_single",
        "get_receipt",
    ]

    return k6.make_configurations(args)


if __name__ == "__main__":
    common.main("etcd", etcd.get_arguments, etcd_configurations, etcd.execute_config)
    common.main("ycsb", ycsb.get_arguments, ycsb_configurations, ycsb.execute_config)
    common.main("perf", perf.get_arguments, perf_configurations, perf.execute_config)
    common.main("k6", k6.get_arguments, k6_configurations, k6.execute_config)
