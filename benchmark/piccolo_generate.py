#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Generate a simple workload to run piccolo with.
"""

import base64
import json
import sys
import time

from generator import Messages
from loguru import logger


# pylint: disable=too-many-arguments
def put(
    msgs: Messages,
    key: str,
    value: str,
    host: str = "127.0.0.1:8000",
    http_version: int = 1,
    count=1,
):
    """
    Add put requests to the messages.
    """
    logger.debug("Adding Put request for key {} and value {}", key, value)
    request_type = "HTTP/1.1" if http_version == 1 else "HTTP/2"
    msgs.append(
        host,
        "/v3/kv/put",
        "POST",
        request_type,
        "application/json",
        json.dumps({"key": b64encode(key), "value": b64encode(value)}),
        count,
    )


# pylint: disable=too-many-arguments
def get(
    msgs: Messages,
    key: str,
    range_end: str = "",
    host: str = "127.0.0.1:8000",
    http_version: int = 1,
    count=1,
):
    """
    Add get requests to the messages.
    """
    data = {"key": b64encode(key)}
    if range_end:
        data["range_end"] = b64encode(range_end)
    logger.debug("Adding Get request for key {} and range_end {}", key, range_end)
    request_type = "HTTP/1.1" if http_version == 1 else "HTTP/2"
    msgs.append(
        host,
        "/v3/kv/range",
        "POST",
        request_type,
        "application/json",
        json.dumps(data),
        count,
    )


# pylint: disable=too-many-arguments
def delete(
    msgs: Messages,
    key: str,
    range_end: str = "",
    host: str = "127.0.0.1:8000",
    http_version: int = 1,
    count=1,
):
    """
    Add delete requests to the messages.
    """
    data = {"key": b64encode(key)}
    if range_end:
        data["range_end"] = b64encode(range_end)
    logger.debug("Adding Delete request for key {} and range_end {}", key, range_end)
    request_type = "HTTP/1.1" if http_version == 1 else "HTTP/2"
    msgs.append(
        host,
        "/v3/kv/delete_range",
        "POST",
        request_type,
        "application/json",
        json.dumps(data),
        count,
    )


def b64encode(string: str) -> str:
    """
    Base64 encode a string.
    """
    return base64.b64encode(string.encode()).decode()


def generate_scenario(http_version: int):
    """
    Generate a scenario for a given http version.
    """
    msgs = Messages()
    # this is slow but could be made faster if the indexes in
    # the Messages dataframe were added at the end as a batch.
    # then we could make one part and repeat it
    start = time.time()
    for i in range(100):
        logger.info("adding batch {}", i)
        for i in range(100):
            key = f"key{i}"
            value = f"value{i}"
            put(msgs, key, value, http_version=http_version)
            get(msgs, key, http_version=http_version)
            delete(msgs, key, http_version=http_version)
    logger.info("took {}", time.time() - start)

    parquet_file = f"piccolo-requests-http{http_version}.parquet"
    logger.info("Writing messages to file {}", parquet_file)
    msgs.to_parquet_file(parquet_file)


def main():
    """
    Run the generator.
    """
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    generate_scenario(1)
    # http2 is not supported yet
    # generate_scenario(2)


if __name__ == "__main__":
    main()
