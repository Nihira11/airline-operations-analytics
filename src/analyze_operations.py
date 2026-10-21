"""Run reproducible business-analysis SQL against a validated monthly database."""

import argparse
import json
from pathlib import Path
import tempfile

import duckdb

from acquire_bts import ROOT, sha256, write_json
from prepare_data import output_reconciliation

THRESHOLDS = {
    "minimum_origin_flights": 1000, "minimum_route_flights": 500,
    "minimum_window_flights": 100, "minimum_common_stratum_flights": 20,
    "minimum_matched_strata": 10, "minimum_matched_arrivals": 1000,
}


def validate_results(results, quality):
    overview = results["overview"][0]
    expected = quality["summary_counts"]
    for name, count_name in [
        ("scheduled_flights", "scheduled_flight_count"), ("cancelled_flights", "cancelled_flight_count"),
        ("diverted_flights", "diverted_flight_count"), ("eligible_arrivals", "eligible_arrival_count"),
        ("on_time_arrivals", "on_time_arrival_count"), ("delayed_arrivals", "delayed_arrival_count"),
    ]:
        if overview[name] != expected[count_name]:
            raise ValueError(f"Overview does not reconcile: {name}")
    for group in ["daily", "airlines", "origins", "routes", "departure_windows"]:
        for measure in ["scheduled_flights", "cancelled_flights", "eligible_arrivals", "on_time_arrivals", "delayed_arrivals"]:
            if sum(row[measure] for row in results[group]) != overview[measure]:
                raise ValueError(f"Grouped totals do not reconcile: {group}/{measure}")
    for rows in results.values():
        for row in rows:
            for name, value in row.items():
                if value is not None and ("rate" in name or name.startswith("coverage_") or name.startswith("share_")):
                    if not 0 <= value <= 1:
                        raise ValueError(f"Rate outside [0, 1]: {name}: {value}")
    if abs(sum(row["share_of_reported_minutes"] for row in results["delay_causes"]) - 1) > 1e-10:
        raise ValueError("Delay-minute category shares do not sum to one")


def lowest(rows, metric, flag, limit=5):
    eligible = [row for row in rows if row[flag] and row[metric] is not None]
    return sorted(eligible, key=lambda row: (row[metric], -row["scheduled_flights"]))[:limit]


def run(year, month):
    period = f"{year}-{month:02d}"
    metadata = ROOT / "data/metadata"
    quality_path = metadata / f"bts_{year}_{month:02d}_quality.json"
    quality = json.loads(quality_path.read_text())
    database_entry = next(item for item in quality["output_files"] if item["path"].endswith(".duckdb"))
    database = ROOT / database_entry["path"]
    if sha256(database) != database_entry["sha256"]:
        raise ValueError("Database differs from the validated preparation output")
    if quality["status"] not in {"passed", "passed_with_warnings"} or any(quality["quality_checks"].values()):
        raise ValueError("Source database has unresolved core validation failures")
    sql_dir = ROOT / "sql/analysis"
    output_dir = database.parent / "analysis"
    connection = duckdb.connect(str(database), read_only=True)
    results = {}
    files = []
    try:
        connection.execute("SET enable_progress_bar=false")
        connection.execute("SET threads=1")
        connection.execute((sql_dir / "00_helpers.sql").read_text())
        for name, value in THRESHOLDS.items():
            connection.execute(f"SET VARIABLE {name} = {value}")
        with tempfile.TemporaryDirectory(prefix=".analysis-", dir=database.parent) as temporary:
            working = Path(temporary)
            for path in sorted(sql_dir.glob("[1-9]*.sql")):
                name = path.stem.split("_", 1)[1]
                query = path.read_text().strip().rstrip(";")
                connection.execute("CREATE OR REPLACE TEMP TABLE analysis_result AS " + query)
                cursor = connection.execute("SELECT * FROM analysis_result")
                columns = [column[0] for column in cursor.description]
                results[name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
                output = working / f"{name}.csv"
                connection.execute("COPY analysis_result TO ? (HEADER true)", [str(output)])
                output_reconciliation(connection, "analysis_result", output, "csv")
                files.append({"path": str((output_dir / output.name).relative_to(ROOT)),
                              "rows": len(results[name]), "sha256": sha256(output)})
            validate_results(results, quality)
            # Source-level cross-check for category minutes; no fill of missing causes.
            source_cause_minutes = connection.execute("""
                SELECT sum(CarrierDelay + WeatherDelay + NASDelay + SecurityDelay + LateAircraftDelay)
                FROM staging.source_flights WHERE NOT Cancelled AND NOT Diverted AND ArrDel15
            """).fetchone()[0]
            if sum(row["reported_delay_minutes"] for row in results["delay_causes"]) != source_cause_minutes:
                raise ValueError("Delay-category minutes differ from typed source")
            output_dir.mkdir(parents=True, exist_ok=True)
            for path in working.iterdir():
                path.replace(output_dir / path.name)
        origins = results["origins"]
        routes = results["routes"]
        daily = results["daily"]
        report = {
            "period": period, "status": "passed", "scope": "January-only descriptive pilot" if month == 1 and year == 2025 else "Single-month descriptive analysis",
            "source_database": database_entry, "thresholds": THRESHOLDS,
            "validation": {
                "overview_matches_preparation": True,
                "grouped_totals_match_overview": True,
                "export_round_trips_match": True,
                "delay_minutes_match_typed_source": True,
            },
            "overview": results["overview"][0], "daily": daily, "airlines": results["airlines"],
            "lowest_on_time_origins": lowest(origins, "arrival_on_time_rate", "meets_arrival_volume_threshold"),
            "highest_cancellation_origins": sorted(
                [row for row in origins if row["meets_cancellation_volume_threshold"]],
                key=lambda row: (-row["cancellation_rate"], -row["scheduled_flights"]),
            )[:5],
            "lowest_on_time_routes": lowest(routes, "arrival_on_time_rate", "meets_arrival_volume_threshold"),
            "highest_delay_volume_routes": sorted(routes, key=lambda row: (-row["delayed_arrivals"], row["route"]))[:5],
            "highest_cancellation_day": max(daily, key=lambda row: row["cancellation_rate"]),
            "lowest_on_time_day": min(daily, key=lambda row: row["arrival_on_time_rate"]),
            "delay_causes": results["delay_causes"],
            "common_route_comparisons": [row for row in results["common_route_comparisons"] if row["meets_comparison_threshold"]],
            "exports": files,
            "limitations": [
                "One month cannot establish seasonality, annual rankings, or future predictive performance.",
                "Unadjusted airline/airport rates reflect network, time-window, and calendar mix.",
                "Common-route comparisons standardise route and four-hour departure block only; each pair has its own overlap population.",
                "Recorded categories are reported attribution, not an independent causal explanation; weather can affect other categories.",
                "Cancellations/diversions are excluded from arrival on-time denominators and retained in scheduled-flight metrics.",
            ],
            "build_inputs": [{"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
                             for path in [ROOT / "src/analyze_operations.py", *sorted(sql_dir.glob("*.sql"))]],
        }
        report = json.loads(json.dumps(report, default=str))
        write_json(metadata / f"bts_{year}_{month:02d}_analysis.json", report)
        print(json.dumps({"status": "passed", "overview": report["overview"],
                          "highest_cancellation_day": report["highest_cancellation_day"],
                          "lowest_on_time_origins": report["lowest_on_time_origins"],
                          "delay_causes": report["delay_causes"]}, indent=2, default=str))
        return report
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--month", type=int, choices=range(1, 13), default=1)
    args = parser.parse_args()
    run(args.year, args.month)


if __name__ == "__main__":
    main()
