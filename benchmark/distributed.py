#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run distributed benchmarks.
"""

import argparse
from typing import List

# pylint: disable=duplicate-code
from loguru import logger
import common
import etcd
import k6
import perf_system as perf
import ycsb


def get_hosts() -> List[str]:
    """
    Get the list of host ip addresses.
    """
    lines = []
    with open("hosts", "r", encoding="utf-8") as hosts:
        lines = [l.strip() for l in hosts.readlines()]
    # skip the runner
    return lines[1:]


def get_nodes() -> List[str]:
    """
    Get the list of node addresses.
    """
    return [f"ssh://{ip}:8000" for ip in get_hosts()]


def common_configurations(args: argparse.Namespace):
    """
    Fill in the args for all common configurations.
    """
    args.worker_threads = [0]
    args.etcd = True
    args.enclave = ["virtual"]
    args.http2 = True
    args.nodes = ["local://127.0.0.1:8000"]


def etcd_configurations(_args: argparse.Namespace) -> List[etcd.EtcdConfig]:
    """
    Set args for all etcd configurations.
    """
    nodes = get_nodes()
    configurations = [
        etcd.EtcdConfig(
            store="lskv",
            tls=True,
            enclave="sgx",
            nodes=nodes,
            worker_threads=0,
            sig_tx_interval=5000,
            sig_ms_interval=1000,
            ledger_chunk_bytes="5MB",
            snapshot_tx_interval=10000,
            http_version=2,
            rate=1000,
            bench_args=["put"],
            clients=100,
            connections=100,
            prefill_num_keys=0,
            prefill_value_size=0,
        ),
        etcd.EtcdConfig(
            store="lskv",
            tls=True,
            enclave="sgx",
            nodes=nodes,
            worker_threads=0,
            sig_tx_interval=5000,
            sig_ms_interval=1000,
            ledger_chunk_bytes="5MB",
            snapshot_tx_interval=10000,
            http_version=2,
            rate=2000,
            bench_args=["put"],
            clients=100,
            connections=100,
            prefill_num_keys=0,
            prefill_value_size=0,
        ),
        etcd.EtcdConfig(
            store="lskv",
            tls=True,
            enclave="sgx",
            nodes=nodes,
            worker_threads=0,
            sig_tx_interval=5000,
            sig_ms_interval=1000,
            ledger_chunk_bytes="5MB",
            snapshot_tx_interval=10000,
            http_version=2,
            rate=3000,
            bench_args=["put"],
            clients=100,
            connections=100,
            prefill_num_keys=0,
            prefill_value_size=0,
        ),
        etcd.EtcdConfig(
            store="lskv",
            tls=True,
            enclave="sgx",
            nodes=nodes,
            worker_threads=0,
            sig_tx_interval=5000,
            sig_ms_interval=1000,
            ledger_chunk_bytes="5MB",
            snapshot_tx_interval=10000,
            http_version=2,
            rate=4000,
            bench_args=["put"],
            clients=100,
            connections=100,
            prefill_num_keys=0,
            prefill_value_size=0,
        ),
        etcd.EtcdConfig(
            store="lskv",
            tls=True,
            enclave="sgx",
            nodes=nodes,
            worker_threads=0,
            sig_tx_interval=5000,
            sig_ms_interval=1000,
            ledger_chunk_bytes="5MB",
            snapshot_tx_interval=10000,
            http_version=2,
            rate=5000,
            bench_args=["put"],
            clients=100,
            connections=100,
            prefill_num_keys=0,
            prefill_value_size=0,
        ),
        etcd.EtcdConfig(
            store="lskv",
            tls=True,
            enclave="sgx",
            nodes=nodes,
            worker_threads=0,
            sig_tx_interval=5000,
            sig_ms_interval=1000,
            ledger_chunk_bytes="5MB",
            snapshot_tx_interval=10000,
            http_version=2,
            rate=6000,
            bench_args=["put"],
            clients=100,
            connections=100,
            prefill_num_keys=0,
            prefill_value_size=0,
        ),
    ]

    return configurations


def ycsb_configurations(_args: argparse.Namespace) -> List[ycsb.YCSBConfig]:
    """
    Set args for all ycsb configurations.
    """
    nodes = get_nodes()
    configurations = (
        [
            # lskv vs etcd
            ycsb.YCSBConfig(
                store="lskv",
                tls=True,
                enclave="sgx",
                nodes=nodes[:3],
                worker_threads=0,
                sig_tx_interval=5000,
                sig_ms_interval=1000,
                ledger_chunk_bytes="5MB",
                snapshot_tx_interval=10000,
                http_version=2,
                rate=10000,
                workload=f"workload{workload}",
                threads=10,
            )
            for workload in ["a", "b", "c", "d", "e", "f"]
        ]
        + [
            # lskv vs etcd
            ycsb.YCSBConfig(
                store="lskv",
                tls=True,
                enclave="virtual",
                nodes=nodes[:3],
                worker_threads=0,
                sig_tx_interval=5000,
                sig_ms_interval=1000,
                ledger_chunk_bytes="5MB",
                snapshot_tx_interval=10000,
                http_version=2,
                rate=10000,
                workload=f"workload{workload}",
                threads=10,
            )
            for workload in ["a", "b", "c", "d", "e", "f"]
        ]
        + [
            ycsb.YCSBConfig(
                store="etcd",
                tls=True,
                enclave="virtual",
                nodes=nodes[:3],
                worker_threads=0,
                sig_tx_interval=5000,
                sig_ms_interval=1000,
                ledger_chunk_bytes="5MB",
                snapshot_tx_interval=10000,
                http_version=2,
                rate=10000,
                workload=f"workload{workload}",
                threads=10,
            )
            for workload in ["a", "b", "c", "d", "e", "f"]
        ]
    )

    return configurations


def perf_configurations(args: argparse.Namespace) -> List[perf.PerfConfig]:
    """
    Set args for all perf configurations.
    """
    common_configurations(args)
    args.http1 = True
    args.http2 = False
    args.etcd = False
    args.workloads = ["benchmark/piccolo-requests-http1.parquet"]
    args.max_inflight_requests = [2]

    return perf.make_configurations(args)


def k6_configurations(_args: argparse.Namespace) -> List[k6.K6Config]:
    """
    Set args for all k6 configurations.
    """
    nodes = get_nodes()
    configurations = (
        [
            # http1 json vs http2 json
            k6.K6Config(
                store="lskv",
                tls=True,
                enclave="sgx",
                nodes=nodes[:1],
                worker_threads=0,
                sig_tx_interval=5000,
                sig_ms_interval=1000,
                ledger_chunk_bytes="5MB",
                snapshot_tx_interval=10000,
                http_version=http_version,
                rate=10000,
                vus=100,
                func="mixed_single",
                content_type="json",
                value_size=256,
            )
            for http_version in [1, 2]
        ]
        + [
            # grpc vs json
            k6.K6Config(
                store="lskv",
                tls=True,
                enclave="sgx",
                nodes=nodes[:1],
                worker_threads=0,
                sig_tx_interval=5000,
                sig_ms_interval=1000,
                ledger_chunk_bytes="5MB",
                snapshot_tx_interval=10000,
                http_version=2,
                rate=10000,
                vus=100,
                func="mixed_single",
                content_type=content_type,
                value_size=256,
            )
            for content_type in ["json", "grpc"]
        ]
        + [
            # virtual vs sgx
            k6.K6Config(
                store="lskv",
                tls=True,
                enclave=enclave,
                nodes=nodes[:1],
                worker_threads=0,
                sig_tx_interval=5000,
                sig_ms_interval=1000,
                ledger_chunk_bytes="5MB",
                snapshot_tx_interval=10000,
                http_version=2,
                rate=10000,
                vus=100,
                func="mixed_single",
                content_type="grpc",
                value_size=256,
            )
            for enclave in ["virtual", "sgx"]
        ]
        + [
            # scale test
            k6.K6Config(
                store="lskv",
                tls=True,
                enclave="sgx",
                nodes=nodes,
                worker_threads=0,
                sig_tx_interval=5000,
                sig_ms_interval=1000,
                ledger_chunk_bytes="5MB",
                snapshot_tx_interval=10000,
                http_version=2,
                rate=10000,
                vus=100,
                func="mixed_single",
                content_type="grpc",
                value_size=256,
            )
            for nodes in [nodes[:i] for i in [1, 3, 5, 7] if len(nodes) >= i]
        ]
        + [
            # receipt generation for mixed requests
            k6.K6Config(
                store="lskv",
                tls=True,
                enclave=enclave,
                nodes=nodes[:1],
                worker_threads=0,
                sig_tx_interval=5000,
                sig_ms_interval=1000,
                ledger_chunk_bytes="5MB",
                snapshot_tx_interval=10000,
                http_version=2,
                rate=10000,
                vus=100,
                func="mixed_single_receipt",
                content_type="json",
                value_size=256,
            )
            for enclave in ["virtual", "sgx"]
        ]
    )

    return configurations


if __name__ == "__main__":
    # logger.info("Running etcd")
    # common.main("etcd", etcd.get_arguments, etcd_configurations, etcd.execute_config)
    logger.info("Running ycsb")
    common.main("ycsb", ycsb.get_arguments, ycsb_configurations, ycsb.execute_config)
    # logger.info("Running perf")
    # common.main("perf", perf.get_arguments, perf_configurations, perf.execute_config)
    logger.info("Running k6")
    common.main("k6", k6.get_arguments, k6_configurations, k6.execute_config)
