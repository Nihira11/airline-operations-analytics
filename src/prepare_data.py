"""Validate one acquired month and build a typed DuckDB database and exports."""

import argparse
import csv
from datetime import date
import json
from pathlib import Path
import tempfile

import duckdb

from acquire_bts import ROOT, sha256, write_json
from schema import (
    CLOCK_FIELDS, INTEGER_FIELDS, SIGNED_INTEGER_FIELDS,
    identifier, invalid_token, source_types, token, typed_expression,
)


def counts(connection, query):
    return dict(connection.execute(query).fetchall())


def validate_source_tokens(connection, types):
    expressions = [
        f"count(*) FILTER (WHERE {invalid_token(name, data_type)}) AS {identifier(name)}"
        for name, data_type in types.items()
    ]
    row = connection.execute("SELECT " + ", ".join(expressions) + " FROM raw_tokens").fetchone()
    violations = {name: value for name, value in zip(types, row) if value}
    if violations:
        raise ValueError(f"Invalid source types or HHMM clock values: {violations}")


def duplicates(connection, relation, columns):
    keys = ", ".join(identifier(name) for name in columns)
    groups, extra = connection.execute(f"""
        SELECT count(*), coalesce(sum(n - 1), 0)::BIGINT FROM (
            SELECT count(*) AS n FROM {relation} GROUP BY {keys} HAVING count(*) > 1
        )
    """).fetchone()
    return {"duplicate_groups": groups, "excess_records": extra}


def read_and_stage(connection, csv_path, source_file):
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        headers = next(csv.reader(handle))
    if headers[-1] != "" or "" in headers[:-1]:
        raise ValueError("Expected the documented single trailing unnamed source column")
    types = source_types(headers[:-1])
    physical_types = {name: "VARCHAR" for name in types}
    physical_types["__source_padding"] = "VARCHAR"
    connection.execute("""
        CREATE TEMP TABLE raw_tokens AS
        SELECT row_number() OVER () AS __source_record_number, * FROM read_csv(
            ?, columns=?, auto_detect=false, header=true, delim=',',
            quote='"', escape='"', strict_mode=true, parallel=false
        )
    """, [str(csv_path), physical_types])
    padding_count = connection.execute(
        "SELECT count(*) FROM raw_tokens WHERE __source_padding IS NOT NULL"
    ).fetchone()[0]
    if padding_count:
        raise ValueError("Unnamed source column contains data; refusing to drop it")
    validate_source_tokens(connection, types)
    exact_duplicates = duplicates(connection, "raw_tokens", list(types))
    if exact_duplicates["excess_records"]:
        raise ValueError(f"Exact duplicates require review before publishing: {exact_duplicates}")
    # Parameter binding protects source paths. Source record numbers count data rows, not the header.
    connection.execute("CREATE TEMP TABLE source_lineage(source_file VARCHAR)")
    connection.execute("INSERT INTO source_lineage VALUES (?)", [source_file])
    expressions = [
        f"{typed_expression(name, data_type)} AS {identifier(name)}"
        for name, data_type in types.items()
    ]
    connection.execute("CREATE SCHEMA staging")
    connection.execute(
        "CREATE TABLE staging.source_flights AS SELECT "
        "__source_record_number AS source_record_number, "
        "(SELECT source_file FROM source_lineage) AS source_file, "
        + ", ".join(expressions) + " FROM raw_tokens"
    )
    base_key = [
        "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline",
        "OriginAirportID", "DestAirportID",
    ]
    key_checks = {
        "exact_source_records": exact_duplicates,
        "date_carrier_flight_route": duplicates(connection, "staging.source_flights", base_key),
        "date_carrier_flight_route_scheduled_departure": duplicates(
            connection, "staging.source_flights", base_key + ["CRSDepTime"]
        ),
    }
    if key_checks["date_carrier_flight_route_scheduled_departure"]["excess_records"]:
        raise ValueError(f"Flight identity collisions require review: {key_checks}")
    return types, key_checks


def validate_staging(connection, types):
    expressions = []
    for name in types:
        # A cast must not silently convert observed values into NULL or fill missing data.
        expressions.append(
            f"(SELECT count(*) FROM raw_tokens WHERE {token(name)} IS NULL) "
            f"- (SELECT count(*) FROM staging.source_flights WHERE {identifier(name)} IS NULL) "
            f"AS {identifier(name)}"
        )
    differences = connection.execute("SELECT " + ", ".join(expressions)).fetchone()
    if any(differences):
        raise ValueError("Source missingness changed during type conversion")
    range_checks = {
        name: connection.execute(
            f"SELECT count(*) FROM staging.source_flights WHERE {identifier(name)} < 0"
        ).fetchone()[0]
        for name in sorted(INTEGER_FIELDS - SIGNED_INTEGER_FIELDS)
    }
    # Keep source anomalies visible. Core analytical measures are gated separately;
    # an unused diversion-detail anomaly must not silently remove a valid flight.
    connection.execute("""
        CREATE TABLE staging.source_quality_issues (
            source_record_number BIGINT, source_field VARCHAR,
            issue_code VARCHAR, observed_value VARCHAR
        )
    """)
    for name, count in range_checks.items():
        if count:
            connection.execute(
                "INSERT INTO staging.source_quality_issues "
                f"SELECT source_record_number, ?, 'negative_nonnegative_measure', "
                f"CAST({identifier(name)} AS VARCHAR) FROM staging.source_flights "
                f"WHERE {identifier(name)} < 0", [name],
            )
    return range_checks


def schema_snapshot(connection, types):
    source = []
    null_counts = connection.execute("SELECT " + ", ".join(
        f"count(*) FILTER (WHERE {identifier(name)} IS NULL)" for name in types
    ) + " FROM staging.source_flights").fetchone()
    for (name, data_type), null_count in zip(types.items(), null_counts):
        source.append({"source_field": name, "duckdb_type": data_type, "null_count": null_count})
    return {
        "typed_source_fields": source,
        "analytics_fields": [
            {"name": row[0], "duckdb_type": row[1]}
            for row in connection.execute("DESCRIBE analytics.flights").fetchall()
        ],
        "clock_policy": (
            "Source HHMM strings including 2400 are retained. Local TIME values map 2400 "
            "to 00:00:00 with scheduled 2400 marker flags. No date offset or UTC timestamp is inferred."
        ),
        "missing_policy": "Blank/whitespace source values become NULL; no imputation",
    }


def output_reconciliation(connection, relation, path, file_format):
    if file_format == "parquet":
        connection.read_parquet(str(path)).create_view("exported", replace=True)
    else:
        types = {row[0]: row[1] for row in connection.execute(f"DESCRIBE {relation}").fetchall()}
        connection.read_csv(str(path), columns=types, header=True, auto_detect=False).create_view(
            "exported", replace=True
        )
    # Compare both directions and multiplicities, not merely aggregate totals.
    different = connection.execute(f"""
        SELECT count(*) FROM (
            (SELECT * FROM {relation} EXCEPT ALL SELECT * FROM exported)
            UNION ALL
            (SELECT * FROM exported EXCEPT ALL SELECT * FROM {relation})
        )
    """).fetchone()[0]
    if different:
        raise ValueError(f"Export differs from its source relation: {path.name}: {different}")
    return connection.execute("SELECT count(*) FROM exported").fetchone()[0]


def build(year, month):
    period = f"{year}-{month:02d}"
    metadata_dir = ROOT / "data" / "metadata"
    manifest_path = metadata_dir / f"bts_{year}_{month:02d}_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    source = next(member for member in manifest["members"] if member["path"].endswith(".csv"))
    csv_path = ROOT / source["path"]
    if sha256(csv_path) != source["sha256"]:
        raise ValueError("Raw CSV no longer matches its acquisition checksum")
    if manifest["period"] != period:
        raise ValueError("Requested month differs from acquisition manifest")
    processed = ROOT / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    output_dir = processed / period
    with tempfile.TemporaryDirectory(prefix=f".build-{period}-", dir=processed) as temporary:
        working = Path(temporary)
        connection = duckdb.connect(str(working / "airline_operations.duckdb"))
        connection.execute("SET enable_progress_bar=false")
        connection.execute("SET threads=4")
        connection.execute("SET memory_limit='1GB'")
        connection.execute("SET preserve_insertion_order=true")
        try:
            print(f"Validating and typing {period} source records", flush=True)
            types, key_checks = read_and_stage(connection, csv_path, source["path"])
            range_checks = validate_staging(connection, types)
            for sql_name in ["01_clean_flights.sql", "02_dimensions_and_exports.sql"]:
                connection.execute((ROOT / "sql" / sql_name).read_text())
            quality_checks = counts(connection, (ROOT / "sql" / "03_quality_checks.sql").read_text())
            row_count = connection.execute("SELECT count(*) FROM analytics.flights").fetchone()[0]
            quality_checks["row_count_difference_from_acquisition"] = abs(row_count - manifest["row_count"])
            quality_checks["joined_export_row_count_difference"] = abs(
                connection.execute("SELECT count(*) FROM analytics.tableau_flights").fetchone()[0] - row_count
            )
            quality_checks["records_outside_requested_month"] = connection.execute(
                "SELECT count(*) FROM analytics.flights WHERE flight_year != ? OR flight_month != ?",
                [year, month],
            ).fetchone()[0]
            failures = {name: value for name, value in quality_checks.items() if value}
            if failures:
                raise ValueError(f"Quality checks failed; outputs were not published: {failures}")
            schema = schema_snapshot(connection, types)
            summary_names = [
                "scheduled_flight_count", "cancelled_flight_count", "diverted_flight_count",
                "eligible_arrival_count", "on_time_arrival_count", "delayed_arrival_count",
            ]
            summary_values = connection.execute("SELECT " + ", ".join(
                f"sum({name})::BIGINT" for name in summary_names
            ) + " FROM analytics.flights").fetchone()
            summary = dict(zip(summary_names, summary_values))
            print(f"Quality checks passed for {row_count:,} rows. Writing and verifying exports.", flush=True)
            output_specs = [
                ("flights.parquet", "analytics.flights", "PARQUET", "source_record_number"),
                ("tableau_flights.csv", "analytics.tableau_flights", "CSV", "flight_date, flight_id"),
                ("daily_operations.csv", "analytics.daily_operations", "CSV", "flight_date, reporting_airline"),
            ]
            exports = []
            for filename, relation, file_format, order in output_specs:
                path = working / filename
                connection.execute(
                    f"COPY (SELECT * FROM {relation} ORDER BY {order}) TO ? "
                    f"(FORMAT {file_format}" + (", HEADER true" if file_format == "CSV" else ", COMPRESSION ZSTD") + ")",
                    [str(path)],
                )
                exported_rows = output_reconciliation(connection, relation, path, file_format.lower())
                exports.append({"path": str((output_dir / filename).relative_to(ROOT)),
                                "row_count": exported_rows, "row_reconciliation": "exact match in both directions"})
            source_clock_counts = {
                name: connection.execute(
                    f"SELECT count(*) FROM staging.source_flights WHERE {identifier(name)} = '2400'"
                ).fetchone()[0] for name in sorted(CLOCK_FIELDS)
            }
            extrema = connection.execute("""
                SELECT min(arrival_delay_minutes), max(arrival_delay_minutes),
                    min(departure_delay_minutes), max(departure_delay_minutes)
                FROM analytics.flights
            """).fetchone()
            report = {
                "period": period,
                "status": "passed_with_warnings" if any(range_checks.values()) else "passed",
                "duckdb_version": duckdb.__version__,
                "source_manifest": str(manifest_path.relative_to(ROOT)),
                "source_csv_sha256": source["sha256"],
                "source_named_fields_retained": len(types), "source_rows": manifest["row_count"],
                "cleaned_rows": row_count, "rows_removed": 0,
                "duplicate_checks": key_checks, "quality_checks": quality_checks,
                "nonnegative_source_field_violation_counts": range_checks,
                "source_measurement_issues": [dict(zip(
                    ["source_record_number", "source_field", "issue_code", "observed_value"], row
                )) for row in connection.execute(
                    "SELECT * FROM staging.source_quality_issues ORDER BY source_record_number, source_field"
                ).fetchall()],
                "source_null_counts_preserved": True, "summary_counts": summary,
                "source_2400_counts": source_clock_counts,
                "signed_delay_ranges_minutes": dict(zip([
                    "arrival_min", "arrival_max", "departure_min", "departure_max",
                ], extrema)),
                "dimensions": {
                    "airports": connection.execute("SELECT count(*) FROM analytics.dim_airports").fetchone()[0],
                    "airlines": connection.execute("SELECT count(*) FROM analytics.dim_airlines").fetchone()[0],
                    "provenance": "Observed source-month mappings; not externally enriched master data",
                },
                "exports": exports,
                "limitations": [
                    "January 2025 only; candidate flight key uniqueness is checked per input month.",
                    "Local clock times cannot establish UTC timestamps or cross-airport elapsed durations.",
                    "Statistical outliers are retained; no unsupported upper-bound clipping is applied.",
                    "Cancellation/diversion rows have NULL prediction labels, not negative labels.",
                ],
            }
            connection.execute("CHECKPOINT")
        finally:
            connection.close()
        # Publish only after every type, key, quality and export reconciliation check passes.
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(working.iterdir()):
            if path.is_file():
                path.replace(output_dir / path.name)
        outputs = [output_dir / "airline_operations.duckdb"] + [ROOT / item["path"] for item in exports]
        report["output_files"] = [{
            "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path),
        } for path in outputs]
        report["build_inputs"] = [{
            "path": str(path.relative_to(ROOT)), "sha256": sha256(path),
        } for path in [ROOT / "requirements.txt", ROOT / "src" / "schema.py", ROOT / "src" / "prepare_data.py",
                       *sorted((ROOT / "sql").glob("*.sql"))]]
        write_json(metadata_dir / f"bts_{year}_{month:02d}_curated_schema.json", schema)
        write_json(metadata_dir / f"bts_{year}_{month:02d}_quality.json", report)
        print(json.dumps({"period": period, "status": report["status"], "rows": row_count,
                          "summary_counts": summary, "output_directory": str(output_dir.relative_to(ROOT))}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--month", type=int, choices=range(1, 13), default=1)
    args = parser.parse_args()
    date(args.year, args.month, 1)
    build(args.year, args.month)


if __name__ == "__main__":
    main()
