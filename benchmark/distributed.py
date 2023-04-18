#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Run distributed benchmarks.
"""

import argparse
from typing import List

import common
import etcd
import k6
import ycsb

# pylint: disable=duplicate-code
from loguru import logger


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


def etcd_configurations(_: argparse.Namespace) -> List[etcd.EtcdConfig]:
    """
    Set args for all etcd configurations.
    """
    nodes = get_nodes()
    repeats = 3
    configurations = []
    for repeat in range(1, repeats + 1):
        configurations += [
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
                repeat=repeat,
                tmpfs=True,
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
                repeat=repeat,
                tmpfs=True,
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
                repeat=repeat,
                tmpfs=True,
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
                repeat=repeat,
                tmpfs=True,
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
                repeat=repeat,
                tmpfs=True,
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
                repeat=repeat,
                tmpfs=True,
                rate=6000,
                bench_args=["put"],
                clients=100,
                connections=100,
                prefill_num_keys=0,
                prefill_value_size=0,
            ),
        ]

    return configurations


def ycsb_configurations(_: argparse.Namespace) -> List[ycsb.YCSBConfig]:
    """
    Set args for all ycsb configurations.
    """
    nodes = get_nodes()
    repeats = 3
    configurations = []
    workload_letters = ["a", "b", "c", "d", "e", "f"]
    workloads = [f"workload{l}" for l in workload_letters]
    for repeat in range(1, repeats + 1):
        configurations += (
            [
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
                    repeat=repeat,
                    tmpfs=False,
                    serializable=True,
                    rate=10000,
                    workload=workload,
                    threads=10,
                )
                for workload in workloads
            ]
            + [
                # lskv sgx
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
                    repeat=repeat,
                    tmpfs=True,
                    serializable=True,
                    rate=10000,
                    workload=workload,
                    threads=10,
                )
                for workload in workloads
            ]
            + [
                # lskv virtual
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
                    repeat=repeat,
                    tmpfs=True,
                    serializable=True,
                    rate=10000,
                    workload=workload,
                    threads=10,
                )
                for workload in workloads
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
                    repeat=repeat,
                    tmpfs=True,
                    serializable=True,
                    rate=10000,
                    workload=workload,
                    threads=10,
                )
                for workload in workloads
            ]
            + [
                # lskv sgx
                ycsb.YCSBConfig(
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
                    repeat=repeat,
                    tmpfs=True,
                    serializable=True,
                    rate=10000,
                    workload=workload,
                    threads=10,
                )
                for workload in workloads
            ]
            + [
                # lskv virtual
                ycsb.YCSBConfig(
                    store="lskv",
                    tls=True,
                    enclave="virtual",
                    nodes=nodes[:1],
                    worker_threads=0,
                    sig_tx_interval=5000,
                    sig_ms_interval=1000,
                    ledger_chunk_bytes="5MB",
                    snapshot_tx_interval=10000,
                    http_version=2,
                    repeat=repeat,
                    tmpfs=True,
                    serializable=True,
                    rate=10000,
                    workload=workload,
                    threads=10,
                )
                for workload in workloads
            ]
            + [
                ycsb.YCSBConfig(
                    store="etcd",
                    tls=True,
                    enclave="virtual",
                    nodes=nodes[:1],
                    worker_threads=0,
                    sig_tx_interval=5000,
                    sig_ms_interval=1000,
                    ledger_chunk_bytes="5MB",
                    snapshot_tx_interval=10000,
                    http_version=2,
                    repeat=repeat,
                    tmpfs=True,
                    serializable=True,
                    rate=10000,
                    workload=workload,
                    threads=10,
                )
                for workload in workloads
            ]
        )

    return configurations


def k6_configurations(_: argparse.Namespace) -> List[k6.K6Config]:
    """
    Set args for all k6 configurations.
    """
    nodes = get_nodes()
    repeats = 3
    configurations = []
    for repeat in range(1, repeats + 1):
        configurations += (
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
                    repeat=repeat,
                    tmpfs=True,
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
                    repeat=repeat,
                    tmpfs=True,
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
                    repeat=repeat,
                    tmpfs=True,
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
                    nodes=n,
                    worker_threads=0,
                    sig_tx_interval=5000,
                    sig_ms_interval=1000,
                    ledger_chunk_bytes="5MB",
                    snapshot_tx_interval=10000,
                    http_version=2,
                    repeat=repeat,
                    tmpfs=True,
                    rate=10000,
                    vus=100,
                    func="mixed_single",
                    content_type="grpc",
                    value_size=256,
                )
                for n in [nodes[:i] for i in [1, 3, 5, 7] if len(nodes) >= i]
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
                    repeat=repeat,
                    tmpfs=True,
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
    # logger.info("Running k6")
    # common.main("k6", k6.get_arguments, k6_configurations, k6.execute_config)
