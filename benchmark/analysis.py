#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Analysis utils.
"""

import json
import os
from typing import List, Tuple

import common
import pandas as pd  # type: ignore
import seaborn as sns  # type: ignore


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
        """
        Return the bench directory where results are stored.
        """
        return os.path.join("..", common.BENCH_DIR, self.benchmark)

    def plot_dir(self) -> str:
        """
        Return the plot directory where plots are stored, making it if it doesn't exist.
        """
        plots_dir = os.path.join("..", "plots", self.benchmark)
        if not os.path.exists(plots_dir):
            os.makedirs(plots_dir)
        return plots_dir

    def make_start_ms(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
        """
        Make the start_ms column.
        """
        if self.benchmark == "etcd":
            # fix csv files not being fully complete
            data = data[data["start_micros"] > 1666000000000000].copy()
            start = data["start_micros"].min()

            data["start_micros"] -= start
            data["start_ms"] = data["start_micros"] / 1000
            data.drop(["start_micros"], axis=1, inplace=True)
            return data, start
        if self.benchmark == "ycsb":
            start = data["timestamp_us"].min()
            data["timestamp_us"] -= start
            data["start_ms"] = data["timestamp_us"] / 1000
            data.drop(["timestamp_us"], axis=1, inplace=True)
            return data, 0
        if self.benchmark == "perf":
            start = data["start_us"].min()
            data["start_us"] -= start
            data["start_ms"] = data["start_us"] / 1000
            data.drop(["start_us"], axis=1, inplace=True)
            return data, 0
        if self.benchmark == "k6":
            starts = data["timestamp"]
            start = starts.min()
            starts -= start
            data["start_ms"] = starts / 1000
            data.drop(["timestamp"], axis=1, inplace=True)
            return data, 0
        return data, 0

    def make_end_ms(self, data: pd.DataFrame, start: int) -> pd.DataFrame:
        """
        Make the end_ms column.
        """
        if self.benchmark == "etcd":
            data["end_micros"] -= start
            data["end_ms"] = data["end_micros"] / 1000
            data.drop(["end_micros"], axis=1, inplace=True)
            return data
        if self.benchmark == "ycsb":
            data["end_ms"] = data["start_ms"] + (data["latency_us"] / 1000)
            return data
        if self.benchmark == "perf":
            data["end_ms"] = data["start_ms"] + (data["latency_us"] / 1000)
            return data
        if self.benchmark == "k6":
            data["end_ms"] = data["start_ms"] + data["metric_value"]
            return data
        return data

    def make_latency_ms(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Make the latency_ms column.
        """
        if self.benchmark == "etcd":
            data["latency_ms"] = data["end_ms"] - data["start_ms"]
            return data
        if self.benchmark == "ycsb":
            data["latency_ms"] = data["latency_us"] / 1000
            data.drop(["latency_us"], axis=1, inplace=True)
            return data
        if self.benchmark == "perf":
            data["latency_ms"] = data["latency_us"] / 1000
            data.drop(["latency_us"], axis=1, inplace=True)
            return data
        if self.benchmark == "k6":
            data["latency_ms"] = data["metric_value"]
            return data
        return data

    def get_data(self) -> pd.DataFrame:
        """
        Load the data for the benchmark, adding config values as columns.
        """
        dataframes = []

        bench_dir = self.bench_dir()
        print(f"loading from {bench_dir}")

        for config_hash in os.listdir(bench_dir):
            print(f"processing {config_hash}")
            with open(
                os.path.join(bench_dir, config_hash, "config.json"),
                "r",
                encoding="utf-8",
            ) as config_f:
                config = json.loads(config_f.read())

            file = os.path.join(bench_dir, config_hash, "timings.csv")
            if not os.path.exists(file):
                continue
            dataframe = pd.read_csv(file)

            dataframe, start = self.make_start_ms(dataframe)
            dataframe = self.make_end_ms(dataframe, start)
            dataframe = self.make_latency_ms(dataframe)

            for key, value in config.items():
                if isinstance(value, list):
                    dataframe[key] = "_".join(value)
                else:
                    dataframe[key] = value

            dataframes.append(dataframe)

        return pd.concat(dataframes, ignore_index=True)

    # pylint: disable=too-many-arguments
    def plot_scatter(
        self,
        data: pd.DataFrame,
        x_column="start_ms",
        y_column="latency_ms",
        row=None,
        col=None,
        # pylint: disable=dangerous-default-value
        ignore_vars=[],
        filename="",
    ):
        """
        Plot a scatter graph.
        """
        hue = "vars"

        var, invariant_vars = condense_vars(
            data, [x_column, y_column, row, col, hue] + ignore_vars
        )
        data[hue] = var

        plot = sns.relplot(
            kind="scatter",
            data=data,
            x=x_column,
            y=y_column,
            row=row,
            col=col,
            hue=hue,
            alpha=0.5,
        )

        plot.figure.subplots_adjust(top=0.9)
        plot.figure.suptitle(",".join(invariant_vars))

        # add tick labels to each x axis
        for axes in plot.axes.flatten():
            axes.tick_params(labelbottom=True)

        #     ax.set_xlim([20,21])

        if not filename:
            filename = f"scatter-{x_column}-{y_column}-{row}-{col}-{hue}"

        plot.savefig(os.path.join(self.plot_dir(), f"{filename}.svg"))
        plot.savefig(os.path.join(self.plot_dir(), f"{filename}.jpg"))

        return plot

    # pylint: disable=too-many-arguments
    def plot_ecdf(
        self,
        data: pd.DataFrame,
        x_column="latency_ms",
        row=None,
        col=None,
        # pylint: disable=dangerous-default-value
        ignore_vars=[],
        filename="",
    ):
        """
        Plot an ecdf graph.
        """
        hue = "vars"

        var, invariant_vars = condense_vars(
            data, [x_column, row, col, hue] + ignore_vars
        )
        data[hue] = var

        plot = sns.displot(
            kind="ecdf",
            data=data,
            x=x_column,
            row=row,
            col=col,
            hue=hue,
            alpha=0.5,
        )

        plot.figure.subplots_adjust(top=0.9)
        plot.figure.suptitle(",".join(invariant_vars))

        # add tick labels to each x axis
        for axes in plot.axes.flatten():
            axes.tick_params(labelbottom=True)

        #     ax.set_xlim([20,21])

        if not filename:
            filename = f"ecdf-{x_column}-{row}-{col}-{hue}"

        plot.savefig(os.path.join(self.plot_dir(), f"{filename}.svg"))
        plot.savefig(os.path.join(self.plot_dir(), f"{filename}.jpg"))

        return plot

    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-locals
    def plot_throughput_bar(
        self,
        data: pd.DataFrame,
        row=None,
        col=None,
        # pylint: disable=dangerous-default-value
        ignore_vars=[],
        filename="",
    ):
        """
        Plot a bar graph of throughput.
        """
        hue = "vars"
        x_column = "rate"
        y_column = "achieved_throughput_ratio"

        var, invariant_vars = condense_vars(
            data, [x_column, y_column, row, col, hue] + ignore_vars
        )
        data[hue] = var

        group_cols = ["rate", hue]
        if row:
            group_cols.append(row)
        if col:
            group_cols.append(col)
        data["rate2"] = data["rate"]
        grouped = data.groupby(group_cols)
        throughputs = grouped.first()

        durations = (grouped["end_ms"].max() - grouped["start_ms"].min()) / 1000
        counts = grouped["start_ms"].count()
        achieved_throughput = counts / durations

        throughputs["achieved_throughput_ratio"] = (
            achieved_throughput / throughputs["rate2"]
        )

        throughputs.reset_index(inplace=True)

        plot = sns.catplot(
            kind="bar",
            data=throughputs,
            x=x_column,
            y=y_column,
            row=row,
            col=col,
            hue=hue,
        )

        plot.figure.subplots_adjust(top=0.9)
        plot.figure.suptitle(",".join(invariant_vars))

        # add tick labels to each x axis
        for axes in plot.axes.flatten():
            axes.tick_params(labelbottom=True)

        if not filename:
            filename = f"throughput_bar-{x_column}-{row}-{col}-{hue}"

        plot.savefig(os.path.join(self.plot_dir(), f"{filename}.svg"))
        plot.savefig(os.path.join(self.plot_dir(), f"{filename}.jpg"))

        return plot

    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-locals
    def plot_achieved_throughput_bar(
        self,
        data: pd.DataFrame,
        row=None,
        col=None,
        # pylint: disable=dangerous-default-value
        ignore_vars=[],
        filename="",
    ):
        """
        Plot a bar graph of achieved throughput.
        """
        x_column = "vars"
        y_column = "achieved_throughput"

        var, invariant_vars = condense_vars(
            data, [x_column, y_column, row, col] + ignore_vars
        )
        data[x_column] = var

        group_cols = [x_column]
        if row:
            group_cols.append(row)
        if col:
            group_cols.append(col)
        grouped = data.groupby(group_cols)
        throughputs = grouped.first()

        durations = (grouped["end_ms"].max() - grouped["start_ms"].min()) / 1000
        counts = grouped["start_ms"].count()
        achieved_throughput = counts / durations
        throughputs["achieved_throughput"] = achieved_throughput

        throughputs.reset_index(inplace=True)

        plot = sns.catplot(
            kind="bar",
            data=throughputs,
            x=x_column,
            y=y_column,
            row=row,
            col=col,
        )

        plot.figure.subplots_adjust(top=0.9)
        plot.figure.suptitle(",".join(invariant_vars))

        # add tick labels to each x axis
        for axes in plot.axes.flatten():
            axes.tick_params(labelbottom=True)

        plot.set_xticklabels(rotation=30, horizontalalignment="right")
        plot.fig.tight_layout()

        if not filename:
            filename = f"achieved_throughput_bar-{x_column}-{row}-{col}"

        plot.savefig(os.path.join(self.plot_dir(), f"{filename}.svg"))
        plot.savefig(os.path.join(self.plot_dir(), f"{filename}.jpg"))

        return plot

    def plot_target_throughput_latency_line(
        self,
        data: pd.DataFrame,
        row=None,
        col=None,
        # pylint: disable=dangerous-default-value
        ignore_vars=[],
        filename="",
    ):
        """
        Plot a line plot of target throughput vs latency.
        """
        x_column = "rate"
        y_column = "latency_ms"
        hue = "vars"

        var, invariant_vars = condense_vars(
            data, [x_column, y_column, row, col, hue] + ignore_vars
        )
        data[hue] = var

        plot = sns.relplot(
            kind="line", data=data, x=x_column, y=y_column, hue=hue, row=row, col=col
        )

        plot.figure.subplots_adjust(top=0.9)
        plot.figure.suptitle(",".join(invariant_vars))

        # add tick labels to each x axis
        for axes in plot.axes.flatten():
            axes.tick_params(labelbottom=True)

        if not filename:
            filename = f"target_throughput_latency_line-{x_column}-{row}-{col}-{hue}"

        plot.figure.savefig(os.path.join(self.plot_dir(), f"{filename}.svg"))
        plot.figure.savefig(os.path.join(self.plot_dir(), f"{filename}.jpg"))

        return plot


def condense_vars(all_data, without) -> Tuple[pd.Series, List[str]]:
    """
    Condense columns into those that have multiple values and those that don't.
    Returning a new series for those that do vary with a string for
    differentiating them and a list of the invariant columns.
    """
    all_columns = list(all_data.columns)
    data_columns = ["start_ms", "end_ms", "latency_ms"]
    # variable columns are all the ones left
    variable_columns = [c for c in all_columns if c not in data_columns]
    remaining_columns = [c for c in variable_columns if c not in without]

    def make_new_column(name):
        if name == "store":
            return all_data[name].astype(str)
        if name == "tls":
            return all_data[name].map(lambda t: "tls" if t else "notls")
        return f"{name}=" + all_data[name].astype(str)

    invariant_columns = []
    variant_columns = []
    for column in remaining_columns:
        data = all_data[column].dropna()
        if len(set(data)) <= 1:
            new_column = make_new_column(column)
            invariant_columns.append(new_column.iat[0])
        else:
            variant_columns.append(column)

    variant_column = pd.Series()
    num_cols = len(variant_columns)
    for i, column in enumerate(variant_columns):
        new_column = make_new_column(column)
        if num_cols != i + 1:
            new_column = new_column + ","
        if i != 0:
            new_column = variant_column + new_column
        variant_column = new_column

    return variant_column, invariant_columns
