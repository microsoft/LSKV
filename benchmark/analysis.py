#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Analysis utils.
"""

import os
from typing import Tuple

import pandas as pd
import seaborn as sns

import common


class Analyser:
    """
    Analyser for helper functions.
    """

    def __init__(self, benchmark: str):
        """
        Initialise analyser.
        """
        self.benchmark = benchmark

    def bench_dir(self) -> str:
        return os.path.join("..", common.BENCH_DIR, self.benchmark)

    def plot_dir(self) -> str:
        d = os.path.join("..", "plots", self.benchmark)
        if not os.path.exists(d):
            os.makedirs(d)
        return d

    def make_start_ms(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
        if self.benchmark == "etcd":
            # fix csv files not being fully complete
            data = data[data["start_micros"] > 1666000000000000].copy()
            start = data["start_micros"].min()

            data["start_micros"] -= start
            data["start_ms"] = data["start_micros"] / 1000
            data.drop(["start_micros"], axis=1, inplace=True)
            return data, start
        elif self.benchmark == "ycsb":
            data["start_ms"] = data["timestamp_us"] / 1000
            data.drop(["timestamp_us"], axis=1, inplace=True)
            return data, 0

    def make_end_ms(self, data: pd.DataFrame, start: int) -> pd.DataFrame:
        if self.benchmark == "etcd":
            data["end_micros"] -= start
            data["end_ms"] = data["end_micros"] / 1000
            data.drop(["end_micros"], axis=1, inplace=True)
            return data
        elif self.benchmark == "ycsb":
            data["end_ms"] = data["start_ms"] + (data["latency_us"] / 1000)
            return data

    def make_latency_ms(self, data: pd.DataFrame) -> pd.DataFrame:
        if self.benchmark == "etcd":
            data["latency_ms"] = data["end_ms"] - data["start_ms"]
            return data
        elif self.benchmark == "ycsb":
            data["latency_ms"] = data["latency_us"] / 1000
            data.drop(["latency_us"], axis=1, inplace=True)
            return data

    def get_data(self) -> pd.DataFrame:
        dfs = []

        bench_dir = self.bench_dir()
        print(f"loading from {bench_dir}")

        for store_config in os.listdir(bench_dir):
            print(f"processing {store_config}")
            parts = store_config.split(",")
            config = {}
            for part in parts:
                kv = part.split("=")
                config[kv[0]] = kv[1]

            file = os.path.join(bench_dir, store_config, "timings.csv")
            if not os.path.exists(file):
                continue
            df = pd.read_csv(file)

            df, start = self.make_start_ms(df)
            df = self.make_end_ms(df, start)
            df = self.make_latency_ms(df)

            for k, v in config.items():
                if v.isdigit():
                    v = int(v)
                df[k] = v

            dfs.append(df)

        return pd.concat(dfs, ignore_index=True)

    def plot_scatter(
        self,
        data: pd.DataFrame,
        x="start_ms",
        y="latency_ms",
        row="",
        col="",
        ignore_vars=[],
        filename="",
    ):
        hue = "vars"

        var, invariant_vars = condense_vars(data, [x, y, row, col, hue] + ignore_vars)
        data[hue] = var

        p = sns.relplot(
            kind="scatter",
            data=data,
            x=x,
            y=y,
            row=row,
            col=col,
            hue=hue,
            alpha=0.5,
        )

        p.figure.subplots_adjust(top=0.9)
        p.figure.suptitle(",".join(invariant_vars))

        # add tick labels to each x axis
        for ax in p.axes.flatten():
            ax.tick_params(labelbottom=True)

        #     ax.set_xlim([20,21])

        if not filename:
            filename = f"scatter-{x}-{y}-{row}-{col}-{hue}"

        p.savefig(os.path.join(self.plot_dir(), f"{filename}.svg"))
        p.savefig(os.path.join(self.plot_dir(), f"{filename}.jpg"))

        return p

    def plot_ecdf(
        self,
        data: pd.DataFrame,
        x="latency_ms",
        row="",
        col="",
        ignore_vars=[],
        filename="",
    ):
        hue = "vars"

        var, invariant_vars = condense_vars(data, [x, row, col, hue] + ignore_vars)
        data[hue] = var

        p = sns.displot(
            kind="ecdf",
            data=data,
            x=x,
            row=row,
            col=col,
            hue=hue,
            alpha=0.5,
        )

        p.figure.subplots_adjust(top=0.9)
        p.figure.suptitle(",".join(invariant_vars))

        # add tick labels to each x axis
        for ax in p.axes.flatten():
            ax.tick_params(labelbottom=True)

        #     ax.set_xlim([20,21])

        if not filename:
            filename = f"ecdf-{x}-{row}-{col}-{hue}"

        p.savefig(os.path.join(self.plot_dir(), f"{filename}.svg"))
        p.savefig(os.path.join(self.plot_dir(), f"{filename}.jpg"))

        return p

    def plot_throughput_bar(
        self, data: pd.DataFrame, row="", col="", ignore_vars=[], filename=""
    ):
        hue = "vars"
        x = "rate"
        y = "achieved_throughput_ratio"

        var, invariant_vars = condense_vars(data, [x, y, row, col, hue] + ignore_vars)
        data[hue] = var

        grouped = data.groupby([hue, row, col])
        throughputs = grouped.first()

        durations = (grouped["end_ms"].max() - grouped["start_ms"].min()) / 1000
        counts = grouped["start_ms"].count()
        achieved_throughput = counts / durations
        throughputs["achieved_throughput_ratio"] = (
            achieved_throughput / throughputs["rate"]
        )

        throughputs.reset_index(inplace=True)

        p = sns.catplot(
            kind="bar",
            data=throughputs,
            x=x,
            y=y,
            row=row,
            col=col,
            hue=hue,
        )

        p.figure.subplots_adjust(top=0.9)
        p.figure.suptitle(",".join(invariant_vars))

        # add tick labels to each x axis
        for ax in p.axes.flatten():
            ax.tick_params(labelbottom=True)

        if not filename:
            filename = f"throughput_bar-{x}-{row}-{col}-{hue}"

        p.savefig(os.path.join(self.plot_dir(), f"{filename}.svg"))
        p.savefig(os.path.join(self.plot_dir(), f"{filename}.jpg"))

        return p


def condense_vars(all_data, without):
    all_columns = list(all_data.columns)
    data_columns = ["start_ms", "end_ms", "latency_ms"]
    # variable columns are all the ones left
    variable_columns = [c for c in all_columns if c not in data_columns]
    remaining_columns = [c for c in variable_columns if c not in without]

    def make_new_column(name):
        if name == "store":
            return all_data[name].astype(str)
        elif name == "tls":
            return all_data[name].map(lambda t: "tls" if t else "notls")
        else:
            return f"{name}=" + all_data[name].astype(str)

    invariant_columns = []
    variant_columns = []
    for c in remaining_columns:
        data = all_data[c]
        if len(set(data)) == 1:
            n = make_new_column(c)
            invariant_columns.append(n.iat[0])
        else:
            variant_columns.append(c)

    variant_column = pd.Series()
    num_cols = len(variant_columns)
    for i, c in enumerate(variant_columns):
        n = make_new_column(c)
        if num_cols != i + 1:
            n = n + ","
        if i != 0:
            n = variant_column + n
        variant_column = n

    return variant_column, invariant_columns
