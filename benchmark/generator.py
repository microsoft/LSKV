# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
# pylint: disable=line-too-long
# From https://github.com/microsoft/CCF/blob/2b6ac3e06d0398b57e1e52293900ad97723fea92/tests/perf-system/generator/generator.py
"""
Generate requests
"""

# pylint: disable=import-error
import fastparquet as fp  # type: ignore
import pandas as pd  # type: ignore


class Messages:
    """
    Messages that will be processed by the submitter.
    """

    def __init__(self):
        self.requests = pd.DataFrame(columns=["messageID", "request"])

    # pylint: disable=too-many-arguments
    def append(
        self,
        host,
        path,
        verb,
        request_type="HTTP/1.1",
        content_type="application/json",
        data="",
        iterations=1,
    ):
        """
        Create a new df with the contents specified by the arguments,
        append it to self.df and return the new df
        """
        batch_df = pd.DataFrame(columns=["messageID", "request"])
        data_headers = "\r\n"
        if len(data) > 0:
            data_headers = "content-length: " + str(len(data)) + "\r\n\r\n" + data

        df_size = len(self.requests.index)

        for ind in range(iterations):
            batch_df.loc[ind] = [
                str(ind + df_size),
                verb.upper()
                + " "
                + path
                + " "
                + request_type
                + "\r\n"
                + "host: "
                + host
                + "\r\n"
                + "content-type: "
                + content_type.lower()
                + "\r\n"
                + data_headers,
            ]

        self.requests = pd.concat([self.requests, batch_df])
        return batch_df

    def to_parquet_file(self, path):
        """
        Write out the current set of messages to a parquet file for ingestion by the submitter.
        """
        fp.write(path, self.requests)
