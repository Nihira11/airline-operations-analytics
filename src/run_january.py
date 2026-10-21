"""Reproduce January analytics, figures, and checks; leave Tableau authoring to the user."""

import argparse
import subprocess
import sys

from acquire_bts import ROOT
from verify_release import verify_prepared


def run(reuse_prepared=False):
    if reuse_prepared:
        verify_prepared()
    else:
        for name in ["acquire_bts.py", "prepare_data.py"]:
            subprocess.run([sys.executable, str(ROOT / "src" / name), "--year", "2025", "--month", "1"],
                           cwd=ROOT, check=True)
    for name in ["analyze_operations.py", "plot_findings.py"]:
        subprocess.run([sys.executable, str(ROOT / "src" / name), "--year", "2025", "--month", "1"],
                       cwd=ROOT, check=True)
    for pattern in ["test_preparation.py", "test_analysis.py"]:
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"],
                       cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "src/verify_release.py")], cwd=ROOT, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-prepared", action="store_true",
                        help="Verify cached preparation hashes instead of repeating acquisition and preparation")
    run(parser.parse_args().reuse_prepared)
