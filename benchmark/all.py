"""
Run all configurations of the benchmarks
"""

import etcd
import logging
from typing import List
import common
import ycsb
import argparse

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.DEBUG)


def all_etcd_configurations(args:argparse.Namespace)->List[etcd.EtcdConfig]:
    args.bench_args = ["put"]
    args.clients = [1, 10, 100]
    args.connections = [1, 10, 100]
    args.rate = [100, 200, 300]

    args.worker_threads = [1, 2, 4]
    args.virtual = True
    args.sgx = True

    return etcd.make_configurations(args)

def all_ycsb_configurations(args:argparse.Namespace)->List[ycsb.YCSBConfig]:
    args.workloads = ["a", "b", "c", "d", "e", "f"]
    args.rate = [100, 200, 300]

    args.worker_threads = [1, 2, 4]
    args.virtual = True
    args.sgx = True

    return etcd.make_configurations(args)

if __name__== "__main__":
    common.main("etcd", etcd.get_arguments, all_etcd_configurations, etcd.run_etcd)
    common.main("ycsb", ycsb.get_arguments, all_ycsb_configurations, ycsb.run_ycsb)