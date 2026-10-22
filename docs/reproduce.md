# Reproduce the January analytics release

This workflow builds the January 2025 analysis and static figures. Tableau authoring is a separate, user-managed step. The raw archive, extracted CSV, DuckDB database, generated data exports, and virtual environment stay outside Git.

## Set up Python

From the repository root, use Python 3.12 and install the pinned analytics/figure dependencies:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-visuals.txt
```

The acquisition step also uses `curl`. Internet access is required to download the archive initially and install packages. The project does not need a separate database server, an API key, or a Tableau API connection.

## Build the analytics

```bash
.venv/bin/python src/run_january.py
```

The command acquires and inventories the official monthly archive, validates/prepares all records, runs ten SQL analysis queries, produces two PNG/SVG figure pairs, runs 13 preparation/analysis tests, and verifies the release artifacts and local document links. Each process must succeed before the next stage starts. Existing cached archives must match their recorded checksum.

To regenerate analysis and figures using existing prepared data:

```bash
.venv/bin/python src/run_january.py --reuse-prepared
```

This still verifies the raw and prepared file checksums and preparation-code fingerprints. If the prepared data or preparation code changed, rebuild from the first command instead of bypassing the mismatch.

## Inspect the results

| Output | Location |
| --- | --- |
| Typed database | `data/processed/2025-01/airline_operations.duckdb` |
| Analytical flight data | `data/processed/2025-01/flights.parquet` |
| Tableau input | `data/processed/2025-01/tableau_flights.csv` |
| Ten SQL result tables | `data/processed/2025-01/analysis/` |
| Static figures and case study | [January report folder](../reports/2025-01/) |
| Release verification | [Release manifest](../data/metadata/bts_2025_01_release.json) |

With no filters applied, expected results are 539,747 scheduled flights; 522,269 eligible arrivals; 424,139 on-time arrivals; 98,130 delayed arrivals; 16,312 cancellations; and 1,166 diversions. Rounded rates are 81.21% on time, 3.02% cancelled, and 0.22% diverted. All 98,130 delayed eligible arrivals have complete reported category fields. The severity bands reconcile to the eligible and delayed populations separately.

## Run checks separately

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python src/verify_release.py
```

The verifier checks source/output checksums, SQL/preparation fingerprints, the January outcome partition, required report files, and local document links. It reports the analytics status separately from the unfinished Tableau dashboard. It does not open Tableau, inspect screenshots, or assert successful publication.

## Recover from a failure

- **Download failure:** rerun acquisition when the network is available. A partial `.zip.part` is not accepted as the archive.
- **Checksum mismatch:** identify whether data or code changed. Do not edit the recorded hash to force a pass. Rerun the owning acquisition/preparation/analysis stage after resolving the cause.
- **Core data-quality failure:** inspect the failed check and original records. Preparation publishes its outputs only after validation succeeds. A documented, retained source anomaly is distinct from an unresolved core failure.
- **Missing package:** install the pinned requirements into this project's `.venv` and use its Python interpreter.
- **Tableau error:** use the [manual dashboard guide](tableau_guide.md). The analytics workflow creates CSV exports rather than a workbook or extract.

## Finish the portfolio release

Open the current workbook, `tableau/Airline Operations January 2025 - lilac.twb`, and compare its unfiltered and filtered views with the guide's checkpoints. Follow the [Tableau progress notes](tableau_progress.md) to verify durable data and image connections, then save portfolio screenshots into `reports/2025-01/`. If publishing, add the actual Tableau Public link to the README and case study. Until those steps are checked, the repository describes a completed analytics handoff with three authored dashboards awaiting final verification.
