"""Verify the January analytics release without opening or rebuilding Tableau."""

import json
from pathlib import Path
import re

from acquire_bts import ROOT, sha256, write_json


def verify_entries(entries):
    for entry in entries:
        path = ROOT / entry["path"]
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise ValueError(f"Missing or changed verified input/output: {entry['path']}")


def verify_prepared():
    metadata = ROOT / "data/metadata"
    source = json.loads((metadata / "bts_2025_01_manifest.json").read_text())
    quality = json.loads((metadata / "bts_2025_01_quality.json").read_text())
    if source["period"] != "2025-01" or quality["period"] != "2025-01":
        raise ValueError("Expected the January 2025 pilot")
    if quality["status"] not in {"passed", "passed_with_warnings"} or any(quality["quality_checks"].values()):
        raise ValueError("Prepared data has unresolved core quality failures")
    verify_entries([source["archive"], *source["members"], *quality["output_files"], *quality["build_inputs"]])
    if source["row_count"] != quality["cleaned_rows"] or quality["rows_removed"] != 0:
        raise ValueError("Acquired and prepared record populations differ")
    return quality


def verify():
    quality = verify_prepared()
    metadata = ROOT / "data/metadata"
    analysis = json.loads((metadata / "bts_2025_01_analysis.json").read_text())
    if analysis["status"] != "passed" or not all(analysis["validation"].values()):
        raise ValueError("Analysis checks have not passed")
    verify_entries([analysis["source_database"], *analysis["exports"], *analysis["build_inputs"]])
    counts = quality["summary_counts"]
    overview = analysis["overview"]
    if (overview["scheduled_flights"] != counts["scheduled_flight_count"]
            or overview["scheduled_flights"] != overview["eligible_arrivals"]
            + overview["cancelled_flights"] + overview["diverted_flights"]):
        raise ValueError("January flight outcomes do not partition the scheduled population")
    required = [
        ROOT / "reports/2025-01/case_study.md",
        ROOT / "reports/2025-01/operations_overview.png",
        ROOT / "reports/2025-01/operations_overview.svg",
        ROOT / "reports/2025-01/delay_diagnostics.png",
        ROOT / "reports/2025-01/delay_diagnostics.svg",
        ROOT / "docs/data_model.md", ROOT / "docs/reproduce.md",
        ROOT / "docs/tableau_guide.md",
    ]
    for path in required:
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing release artifact: {path.relative_to(ROOT)}")
    # Check local document/image links while leaving external websites out of this local check.
    for path in [ROOT / "README.md", *[p for p in required if p.suffix == ".md"]]:
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            local = target.split("#", 1)[0]
            if (path.parent / local).resolve() == (metadata / "bts_2025_01_release.json").resolve():
                continue  # This verifier writes that linked artifact only after all checks pass.
            if local and not (path.parent / local).exists():
                raise ValueError(f"Broken local link in {path.relative_to(ROOT)}: {target}")
    artifacts = [*required, ROOT / "README.md", ROOT / "src/plot_findings.py",
                 ROOT / "src/run_january.py", ROOT / "src/verify_release.py", ROOT / "requirements-visuals.txt"]
    report = {
        "period": "2025-01", "analytics_status": "verified",
        "complete_portfolio_release_status": "awaiting_user_tableau_dashboard_and_screenshots",
        "source_rows": quality["cleaned_rows"], "core_quality_checks": len(quality["quality_checks"]),
        "source_measurement_issues": len(quality["source_measurement_issues"]),
        "analysis_exports": len(analysis["exports"]),
        "validation": {"source_and_output_checksums": "passed", "build_input_checksums": "passed",
                       "outcome_population_reconciliation": "passed", "local_document_links": "passed"},
        "analysis_manifest_sha256": sha256(metadata / "bts_2025_01_analysis.json"),
        "quality_manifest_sha256": sha256(metadata / "bts_2025_01_quality.json"),
        "artifacts": [{"path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                       "bytes": path.stat().st_size} for path in artifacts],
        "scope": "January descriptive analytics. Full-year data and prediction are deferred.",
        "tableau": "User-managed; no native rendering, interaction, or publishing claim is made by this check.",
    }
    write_json(metadata / "bts_2025_01_release.json", report)
    print(json.dumps({key: value for key, value in report.items() if key != "artifacts"}, indent=2))
    return report


if __name__ == "__main__":
    verify()
