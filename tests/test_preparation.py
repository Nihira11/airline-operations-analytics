"""Boundary and preservation checks using explicitly synthetic flight fixtures."""

from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prepare_data import duplicates, output_reconciliation, validate_source_tokens
from schema import identifier, source_types


class FlightPreparationTests(unittest.TestCase):
    def setUp(self):
        self.connection = duckdb.connect()
        self.connection.execute("SET enable_progress_bar=false")
        fields = [field["name"] for field in json.loads(
            (ROOT / "data/metadata/bts_2025_01_dictionary.json").read_text()
        )["fields"]]
        self.types = source_types(fields)
        self.connection.execute("CREATE SCHEMA staging")
        self.connection.execute(
            "CREATE TABLE staging.source_flights "
            "(source_record_number BIGINT, source_file VARCHAR, "
            + ", ".join(f"{identifier(name)} {kind}" for name, kind in self.types.items()) + ")"
        )
        self.connection.execute("CREATE TABLE staging.source_quality_issues(source_record_number BIGINT)")

    def tearDown(self):
        self.connection.close()

    def flight(self, record=1, **changes):
        row = {
            "source_record_number": record, "source_file": "synthetic-test-fixture.csv",
            "FlightDate": date(2025, 1, 1), "Year": 2025, "Quarter": 1, "Month": 1,
            "DayofMonth": 1, "DayOfWeek": 3, "Reporting_Airline": "AA",
            "DOT_ID_Reporting_Airline": 19805, "Flight_Number_Reporting_Airline": str(record),
            "OriginAirportID": 12478, "DestAirportID": 12892, "Origin": "JFK", "Dest": "LAX",
            "CRSDepTime": "0559", "CRSArrTime": "2400", "CRSElapsedTime": 360,
            "Distance": 2475, "ArrDelay": 0, "Cancelled": False, "Diverted": False,
        }
        row.update(changes)
        self.connection.execute(
            "INSERT INTO staging.source_flights (" + ", ".join(identifier(name) for name in row)
            + ") VALUES (" + ", ".join("?" for _ in row) + ")", list(row.values())
        )

    def clean(self):
        self.connection.execute((ROOT / "sql/01_clean_flights.sql").read_text())

    def test_clock_and_early_arrival_are_preserved(self):
        self.flight(ArrDelay=-7)
        self.clean()
        result = self.connection.execute("""
            SELECT scheduled_departure_hhmm, scheduled_departure_hour,
                CAST(scheduled_arrival_local AS VARCHAR), scheduled_arrival_is_2400,
                arrival_delay_minutes, positive_arrival_delay_minutes, on_time_arrival_count
            FROM analytics.flights
        """).fetchone()
        self.assertEqual(result, ("0559", 5, "00:00:00", True, -7, 0, 1))

    def test_fifteen_minute_threshold(self):
        self.flight(1, ArrDelay=14)
        self.flight(2, ArrDelay=15)
        self.clean()
        self.assertEqual(self.connection.execute("""
            SELECT arrival_delayed_15, on_time_arrival_count, delayed_arrival_count
            FROM analytics.flights ORDER BY source_record_number
        """).fetchall(), [(False, 1, 0), (True, 0, 1)])

    def test_cancellations_and_diversions_do_not_become_on_time_labels(self):
        self.flight(1, ArrDelay=None, Cancelled=True)
        self.flight(2, ArrDelay=None, Diverted=True)
        self.clean()
        self.assertEqual(self.connection.execute("""
            SELECT operation_status, arrival_delayed_15, positive_arrival_delay_minutes,
                scheduled_flight_count, eligible_arrival_count, on_time_arrival_count, delayed_arrival_count
            FROM analytics.flights ORDER BY source_record_number
        """).fetchall(), [("Cancelled", None, None, 1, 0, 0, 0), ("Diverted", None, None, 1, 0, 0, 0)])

    def test_measurement_issue_flags_a_flight_without_removing_it(self):
        self.flight(Diverted=True, ArrDelay=None, DivActualElapsedTime=-175)
        self.connection.execute("INSERT INTO staging.source_quality_issues VALUES (1)")
        self.clean()
        self.assertEqual(self.connection.execute(
            "SELECT count(*), bool_and(has_source_quality_issue) FROM analytics.flights"
        ).fetchone(), (1, True))

    def test_invalid_tokens_are_rejected_instead_of_rounded(self):
        for name, kind, invalid in [
            ("Distance", "INTEGER", "12.5"), ("CRSDepTime", "VARCHAR", "2401"),
            ("Cancelled", "BOOLEAN", "2"), ("FlightDate", "DATE", "2025-02-30"),
        ]:
            with self.subTest(field=name):
                self.connection.execute("DROP TABLE IF EXISTS raw_tokens")
                self.connection.execute(f"CREATE TABLE raw_tokens ({identifier(name)} VARCHAR)")
                self.connection.execute("INSERT INTO raw_tokens VALUES (?)", [invalid])
                with self.assertRaises(ValueError):
                    validate_source_tokens(self.connection, {name: kind})

    def test_valid_midnight_blank_and_decimal_integer_tokens(self):
        self.connection.execute("CREATE TABLE raw_tokens(CRSDepTime VARCHAR, Distance VARCHAR, Cancelled VARCHAR)")
        self.connection.execute("INSERT INTO raw_tokens VALUES ('2400', '12.00', '0.00'), (NULL, NULL, NULL)")
        validate_source_tokens(self.connection, {"CRSDepTime": "VARCHAR", "Distance": "INTEGER", "Cancelled": "BOOLEAN"})

    def test_duplicate_counter_preserves_multiplicity(self):
        self.connection.execute("CREATE TABLE sample(a INTEGER, b VARCHAR)")
        self.connection.execute("INSERT INTO sample VALUES (1, 'x'), (1, 'x'), (1, 'y')")
        self.assertEqual(duplicates(self.connection, "sample", ["a"]),
                         {"duplicate_groups": 1, "excess_records": 2})
        self.assertEqual(duplicates(self.connection, "sample", ["a", "b"]),
                         {"duplicate_groups": 1, "excess_records": 1})

    def test_csv_round_trip_keeps_leading_zeros_nulls_and_duplicates(self):
        self.connection.execute("CREATE TABLE sample(code VARCHAR, value INTEGER)")
        self.connection.execute("INSERT INTO sample VALUES ('06', NULL), ('06', NULL), ('01', -7)")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.csv"
            self.connection.execute("COPY sample TO ? (HEADER true)", [str(path)])
            self.assertEqual(output_reconciliation(self.connection, "sample", path, "csv"), 3)
            path.write_text("code,value\n6,\n06,\n01,-7\n")
            with self.assertRaises(ValueError):
                output_reconciliation(self.connection, "sample", path, "csv")


if __name__ == "__main__":
    unittest.main()
