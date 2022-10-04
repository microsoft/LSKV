#!/bin/bash

set -xe

is_package_specified=false
is_js_bundle_specified=false

extra_args=("$@")
while [ "$1" != "" ]; do
    case $1 in
        -p|--package)
            is_package_specified=true
            shift
            ;;
        -p=*|--package=*)
            is_package_specified=true
            ;;
        --js-app-bundle)
            is_js_bundle_specified=true
            shift
            ;;
        --js-app-bundle=*)
            is_js_bundle_specified=true
            ;;
        *)
            ;;
    esac
    shift
done

if [ ${is_package_specified} == false ] && [ ${is_js_bundle_specified} == false ]; then
    # Only on install tree, default to installed js logging app
    echo "No package/app specified. Defaulting to installed JS logging app"
    extra_args+=(--package "CCF_ROOT/lib/libjs_generic")
    extra_args+=(--js-app-bundle "CCF_ROOT/samples/logging/js")
fi

PATH_HERE=$(dirname "$(realpath -s "$0")")

START_NETWORK_SCRIPT \
    --binary-dir CCF_ROOT/bin \
    --oe-binary OE_ROOT/bin \
    --enclave-type virtual \
    --initial-member-count 1 \
    --constitution "${PATH_HERE}"/actions.js \
    --constitution "${PATH_HERE}"/validate.js \
    --constitution "${PATH_HERE}"/resolve.js \
    --constitution "${PATH_HERE}"/apply.js \
    --ledger-chunk-bytes 5000000 \
    --snapshot-tx-interval 10000 \
    --initial-node-cert-validity-days 90 \
    --initial-service-cert-validity-days 90 \
    --label sandbox \
    "${extra_args[@]}"

