"""Create publication-ready static figures from the validated SQL results."""

import argparse
from datetime import date
import json
import os
from pathlib import Path

from acquire_bts import ROOT

os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data/processed/.matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, PercentFormatter


def plot(year, month):
    report = json.loads((ROOT / f"data/metadata/bts_{year}_{month:02d}_analysis.json").read_text())
    if report["status"] != "passed":
        raise ValueError("Analysis must pass validation before plotting")
    output = ROOT / "reports" / f"{year}-{month:02d}"
    output.mkdir(parents=True, exist_ok=True)
    blue, orange, ink, grid = "#246a91", "#bd5726", "#223447", "#e6ebf0"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.labelcolor": ink, "text.color": ink, "axes.titleweight": "bold",
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "airline-operations-2025"})
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="white")
    fig.subplots_adjust(top=0.83, bottom=0.20, left=0.09, right=0.96, hspace=0.58, wspace=0.38)
    overview = report["overview"]
    period = date(year, month, 1).strftime("%B %Y")
    fig.text(0.09, 0.95, f"{period} | Airline reliability", fontsize=24, weight="bold")
    fig.text(0.09, 0.90,
             f"{overview['scheduled_flights']:,} scheduled flights     "
             f"{overview['arrival_on_time_rate']:.2%} arrival on time     "
             f"{overview['cancellation_rate']:.2%} cancelled", fontsize=13, color=ink)
    dates = [date.fromisoformat(row["flight_date"]) for row in report["daily"]]
    ax = axes[0, 0]
    ax.plot(dates, [row["arrival_on_time_rate"] for row in report["daily"]], color=blue, linewidth=2.2)
    ax.set(title="Arrival reliability by day", ylabel="On-time arrivals / eligible arrivals", xlabel="Flight date")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.xaxis.set_major_locator(FixedLocator(mdates.date2num(dates[::5])))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax = axes[0, 1]
    rates = [row["cancellation_rate"] for row in report["daily"]]
    ax.bar(dates, rates, color=orange, width=0.78)
    peak = report["highest_cancellation_day"]
    peak_date = date.fromisoformat(peak["flight_date"])
    ax.annotate(f"{peak_date:%d %b}: {peak['cancellation_rate']:.2%}\n{peak['cancelled_flights']:,} cancellations",
                xy=(peak_date, peak["cancellation_rate"]), xytext=(12, 12),
                textcoords="offset points", fontsize=10, color=ink)
    ax.set(title="Cancellation rate by day", ylabel="Cancelled / scheduled flights", xlabel="Flight date")
    ax.set_ylim(0, max(rates) * 1.40)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.xaxis.set_major_locator(FixedLocator(mdates.date2num(dates[::5])))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax = axes[1, 0]
    origins = report["lowest_on_time_origins"][::-1]
    labels = [row["airport"] for row in origins]
    values = [row["arrival_on_time_rate"] for row in origins]
    ax.barh(labels, values, color=blue, height=0.62)
    for index, row in enumerate(origins):
        ax.text(row["arrival_on_time_rate"] + 0.012, index,
                f"{row['arrival_on_time_rate']:.1%}  (n={row['eligible_arrivals']:,})", va="center", fontsize=9)
    ax.set(title="Lowest arrival on-time rates by origin", xlabel="On-time arrivals / eligible arrivals", ylabel="Origin airport")
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax = axes[1, 1]
    causes = report["delay_causes"][::-1]
    ax.barh([row["category"] for row in causes], [row["share_of_reported_minutes"] for row in causes],
            color=blue, height=0.62)
    for index, row in enumerate(causes):
        ax.text(row["share_of_reported_minutes"] + 0.008, index,
                f"{row['share_of_reported_minutes']:.2%}", va="center", fontsize=9)
    ax.set(title="Share of reported delay-category minutes", xlabel="Category minutes / all reported category minutes")
    ax.set_xlim(0, 0.46)
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    for ax in axes.flat:
        ax.grid(axis="y" if ax in axes[0] else "x", color=grid, linewidth=0.8)
        ax.set_axisbelow(True)
    fig.text(0.09, 0.035,
             "Source: US DOT / BTS Reporting Carrier On-Time Performance. January 2025 descriptive pilot.\n"
             "Eligible arrivals exclude cancellations and diversions. On time means arrival delay <15 minutes.\n"
             "Origin comparisons require at least 1,000 eligible arrivals; n is the eligible-arrival count.\n"
             "Reported categories describe attribution; comparisons reflect network and calendar mix.", fontsize=9, linespacing=1.7)
    fig.savefig(output / "operations_overview.png", dpi=160)
    fig.savefig(output / "operations_overview.svg", metadata={"Date": None})
    plt.close(fig)
    print(output / "operations_overview.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--month", type=int, default=1)
    args = parser.parse_args()
    plot(args.year, args.month)
