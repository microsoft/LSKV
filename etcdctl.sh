#!/usr/bin/env sh

set -e

bindir=bin

install_etcdctl() {
    ETCD_VER="v3.5.4"

    GITHUB_URL=https://github.com/etcd-io/etcd/releases/download
    DOWNLOAD_URL=${GITHUB_URL}

    rm -f /tmp/etcd-${ETCD_VER}-linux-amd64.tar.gz
    rm -rf /tmp/etcd-download-test && mkdir -p /tmp/etcd-download-test

    curl -L ${DOWNLOAD_URL}/${ETCD_VER}/etcd-${ETCD_VER}-linux-amd64.tar.gz -o /tmp/etcd-${ETCD_VER}-linux-amd64.tar.gz
    tar xzvf /tmp/etcd-${ETCD_VER}-linux-amd64.tar.gz -C /tmp/etcd-download-test --strip-components=1
    rm -f /tmp/etcd-${ETCD_VER}-linux-amd64.tar.gz

    mkdir -p $bindir
    mv /tmp/etcd-download-test/etcdctl $bindir/etcdctl
}

if [ ! -f "$bindir/etcdctl" ]; then
    install_etcdctl
fi

workspace_common=workspace/sandbox_common

cmd="$bindir/etcdctl --endpoints=https://127.0.0.1:8000 --cacert=$workspace_common/service_cert.pem --cert=$workspace_common/user0_cert.pem --key=$workspace_common/user0_privk.pem $@"
echo $cmd
$cmd
