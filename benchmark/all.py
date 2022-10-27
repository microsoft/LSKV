#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run all configurations of the benchmarks
"""

import argparse
from typing import List

import common
import etcd
import perf_system
import ycsb


def all_common_configurations(args: argparse.Namespace):
    """
    Fill in the args for all common configurations.
    """
    args.nodes = [1, 3, 5]
    args.worker_threads = [1, 2, 4]
    args.virtual = True
    args.sgx = True
    args.http2 = True

    args.sig_tx_intervals = [5000, 10000, 20000]
    args.sig_ms_intervals = [100, 1000, 10000]
    args.ledger_chunk_bytes = ["20KB", "100KB", "1MB"]
    args.snapshot_tx_intervals = [10, 100, 1000]


def all_etcd_configurations(args: argparse.Namespace) -> List[etcd.EtcdConfig]:
    """
    Set args for all etcd configurations.
    """
    args.bench_args = [
        ["put"],
        ["range", "0000", "1000"],
        ["txn-put"],
        ["txn-mixed", "txn-mixed-key"],
    ]
    args.clients = [1, 10, 100]
    args.connections = [1, 10, 100]
    args.rate = [100, 200, 300]

    all_common_configurations(args)
    return etcd.make_configurations(args)


def all_ycsb_configurations(args: argparse.Namespace) -> List[ycsb.YCSBConfig]:
    """
    Set args for all ycsb configurations.
    """
    args.workloads = ["a", "b", "c", "d", "e", "f"]
    args.rate = [100, 200, 300]
    args.threads = [1, 2, 4]

    all_common_configurations(args)
    return ycsb.make_configurations(args)


def all_perf_configurations(args: argparse.Namespace) -> List[perf_system.PerfConfig]:
    """
    Set args for all perf configurations.
    """
    args.http1 = True

    all_common_configurations(args)
    return perf_system.make_configurations(args)


if __name__ == "__main__":
    common.main(
        "etcd", etcd.get_arguments, all_etcd_configurations, etcd.execute_config
    )
    common.main(
        "ycsb", ycsb.get_arguments, all_ycsb_configurations, ycsb.execute_config
    )
    common.main(
        "perf",
        perf_system.get_arguments,
        all_perf_configurations,
        perf_system.execute_config,
    )
