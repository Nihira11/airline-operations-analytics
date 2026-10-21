"""Exercise the actual Hyper file conversion, including missing values and types."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tableau_extracts import create_extract


class TableauExtractTests(unittest.TestCase):
    def test_types_nulls_duplicates_and_quoted_paths_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="airline's-") as temporary:
            directory = Path(temporary)
            csv_path = directory / "input's.csv"
            csv_path.write_text(
                'label,day,clock,flag,integer,bigint,real\n'
                '"O\'Hare, Chicago",2025-01-01,23:59:00,true,-1,9223372036854775806,0.123456789012345\n'
                '"O\'Hare, Chicago",2025-01-01,23:59:00,true,-1,9223372036854775806,0.123456789012345\n'
                ',,,,0,,\n', encoding="utf-8"
            )
            report = create_extract(csv_path, {
                "label": "VARCHAR", "day": "DATE", "clock": "TIME", "flag": "BOOLEAN",
                "integer": "INTEGER", "bigint": "BIGINT", "real": "DOUBLE",
            }, directory / "output.hyper")
            self.assertEqual(report["rows"], 3)
            self.assertEqual(report["typed_multiset_round_trip"], "passed")
            self.assertGreater(report["bytes"], 0)

    def test_header_mismatch_preserves_previous_extract(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            csv_path = directory / "input.csv"
            csv_path.write_text("wrong\n1\n", encoding="utf-8")
            destination = directory / "output.hyper"
            destination.write_bytes(b"previous extract")
            with self.assertRaisesRegex(ValueError, "header"):
                create_extract(csv_path, {"expected": "INTEGER"}, destination)
            self.assertEqual(destination.read_bytes(), b"previous extract")


if __name__ == "__main__":
    unittest.main()
