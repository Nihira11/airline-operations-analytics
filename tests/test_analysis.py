"""Check weighted comparison logic with deliberately synthetic strata."""

from pathlib import Path
import sys
import unittest

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from analyze_operations import THRESHOLDS


class BusinessAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.connection = duckdb.connect()
        self.connection.execute((ROOT / "sql/analysis/00_helpers.sql").read_text())
        self.connection.execute("CREATE SCHEMA analytics")
        self.connection.execute("""
            CREATE TABLE analytics.flights(reporting_airline VARCHAR, route VARCHAR,
                scheduled_departure_hour INTEGER, eligible_arrival_count INTEGER, on_time_arrival_count INTEGER)
        """)
        # Carrier A performs better in both strata, but has more exposure to the harder route.
        self.connection.execute("""
            INSERT INTO analytics.flights VALUES
                ('A', 'X-Y', 8, 10, 9), ('A', 'Z-Y', 8, 100, 20),
                ('B', 'X-Y', 8, 100, 80), ('B', 'Z-Y', 8, 10, 1)
        """)
        for name in THRESHOLDS:
            self.connection.execute(f"SET VARIABLE {name} = 1")

    def tearDown(self):
        self.connection.close()

    def compare(self):
        cursor = self.connection.execute((ROOT / "sql/analysis/17_common_route_comparisons.sql").read_text())
        return dict(zip([column[0] for column in cursor.description], cursor.fetchone()))

    def test_shared_weights_remove_the_synthetic_mix_reversal(self):
        row = self.compare()
        self.assertLess(row["raw_gap_a_minus_b"], 0)
        self.assertAlmostEqual(row["standardised_on_time_rate_a"], 0.55)
        self.assertAlmostEqual(row["standardised_on_time_rate_b"], 0.45)
        self.assertAlmostEqual(row["standardised_gap_a_minus_b"], 0.10)
        self.assertEqual((row["coverage_a"], row["coverage_b"]), (1, 1))

    def test_overlap_threshold_is_applied(self):
        self.connection.execute("SET VARIABLE minimum_matched_strata = 3")
        self.assertFalse(self.compare()["meets_comparison_threshold"])

    def test_zero_denominators_remain_unavailable(self):
        self.assertIsNone(self.connection.execute("SELECT safe_rate(0, 0)").fetchone()[0])
        self.assertAlmostEqual(self.connection.execute("SELECT safe_rate(1, 4)").fetchone()[0], 0.25)


if __name__ == "__main__":
    unittest.main()
