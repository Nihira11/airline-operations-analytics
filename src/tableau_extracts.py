"""Build Tableau Hyper extracts and reconcile every exported row with its input."""

import csv
from pathlib import Path
import tempfile

import duckdb
from tableauhyperapi import (
    Connection, CreateMode, HyperProcess, SqlType, TableDefinition, TableName,
    Telemetry, escape_string_literal,
)

from acquire_bts import sha256
from schema import identifier


def create_extract(csv_path, schema, destination):
    """Only replace the destination after a full typed multiset round-trip check."""
    with csv_path.open(encoding="utf-8", newline="") as handle:
        if next(csv.reader(handle)) != list(schema):
            raise ValueError(f"Extract schema does not match the CSV header: {csv_path.name}")
    hyper_types = {
        "VARCHAR": SqlType.text(), "TIME": SqlType.text(), "DATE": SqlType.date(),
        "BOOLEAN": SqlType.bool(), "INTEGER": SqlType.int(), "BIGINT": SqlType.big_int(),
        "HUGEINT": SqlType.big_int(), "DOUBLE": SqlType.double(),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hyper-", dir=destination.parent) as temporary:
        working = Path(temporary)
        extract_path = working / destination.name
        round_trip = working / "round_trip.csv"
        table = TableDefinition(TableName("Extract", "Extract"), [
            TableDefinition.Column(name, hyper_types[kind]) for name, kind in schema.items()
        ])
        with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                          parameters={"log_dir": str(working), "default_database_version": "2"}) as hyper:
            with Connection(hyper.endpoint, extract_path, CreateMode.CREATE_AND_REPLACE) as connection:
                connection.catalog.create_schema("Extract")
                connection.catalog.create_table(table)
                connection.execute_command(
                    f"COPY {table.table_name} FROM {escape_string_literal(str(csv_path.resolve()))} "
                    "WITH (format csv, delimiter ',', header, null '')"
                )
            # Reopen the completed file rather than verifying only the insertion connection.
            with Connection(hyper.endpoint, extract_path) as connection:
                row_count = connection.execute_scalar_query(f"SELECT count(*) FROM {table.table_name}")
                connection.execute_command(
                    f"COPY {table.table_name} TO {escape_string_literal(str(round_trip))} "
                    "WITH (format csv, delimiter ',', header, null '')"
                )
                kpis = None
                if "scheduled_flight_count" in schema:
                    names = ["scheduled_flight_count", "on_time_arrival_count", "eligible_arrival_count",
                             "cancelled_flight_count", "diverted_flight_count"]
                    values = connection.execute_list_query(
                        "SELECT " + ", ".join(f"sum({identifier(name)})" for name in names)
                        + f" FROM {table.table_name}"
                    )[0]
                    kpis = dict(zip(names, values))
        # Clocks stay strings, exactly as used by the workbook's CSV connection.
        types = {name: "VARCHAR" if kind == "TIME" else kind for name, kind in schema.items()}
        with duckdb.connect() as check:
            check.execute("SET threads=2")
            for view, path in [("original", csv_path), ("exported", round_trip)]:
                check.read_csv(str(path), columns=types, header=True, auto_detect=False).create_view(view)
            different = check.execute("""
                SELECT count(*) FROM (
                    (SELECT * FROM original EXCEPT ALL SELECT * FROM exported)
                    UNION ALL
                    (SELECT * FROM exported EXCEPT ALL SELECT * FROM original)
                )
            """).fetchone()[0]
            expected_count = check.execute("SELECT count(*) FROM original").fetchone()[0]
        if different or row_count != expected_count:
            raise ValueError(f"Hyper extract differs from input: {csv_path.name}: {different} rows")
        extract_path.replace(destination)
    return {"rows": row_count, "columns": len(schema), "sha256": sha256(destination),
            "bytes": destination.stat().st_size, "typed_multiset_round_trip": "passed",
            "kpi_counts": kpis, "telemetry": "disabled"}
