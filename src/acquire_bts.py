"""Download and inventory one BTS reporting-carrier month without extra packages.

Run from any directory: python3 src/acquire_bts.py --year 2025 --month 1
Raw archives and extracted members are preserved locally; metadata is Git-friendly.
"""

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timezone
import hashlib
from html import unescape
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = "https://transtats.bts.gov/PREZIP/"
FIELD_DEFINITIONS = (
    "https://www.transtats.bts.gov/DL_SelectFields.aspx?"
    "QO_fu146_anzr=%5D&gnoyr_VQ=FGJ"
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def acquire(year, month):
    name = (
        "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_"
        f"{year}_{month}.zip"
    )
    archive = ROOT / "data" / "raw" / name
    manifest_path = ROOT / "data" / "metadata" / f"bts_{year}_{month:02d}_manifest.json"
    source_url = SOURCE_DIRECTORY + name
    archive.parent.mkdir(parents=True, exist_ok=True)

    if not archive.exists():
        temporary = archive.with_suffix(".zip.part")
        print(f"Downloading {source_url}", flush=True)
        subprocess.run(
            [
                "curl", "--fail", "--location", "--silent", "--show-error",
                "--retry", "2", "--connect-timeout", "20", "--max-time", "600",
                "--output", str(temporary), source_url,
            ],
            check=True,
        )
        with zipfile.ZipFile(temporary) as downloaded:
            if downloaded.testzip() is not None:
                raise ValueError("Archive failed its CRC integrity check")
        temporary.replace(archive)

    archive_hash = sha256(archive)
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if previous and previous["archive"]["sha256"] != archive_hash:
        raise ValueError("Cached archive differs from the recorded SHA-256 checksum")

    members = []
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise ValueError("Archive failed its CRC integrity check")
        for info in zipped.infolist():
            if info.is_dir():
                continue
            # Never allow ZIP member paths to escape the raw-data directory.
            if Path(info.filename).name != info.filename:
                raise ValueError(f"Unexpected nested archive member: {info.filename}")
            destination = archive.parent / f"{year}-{month:02d}" / info.filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".part")
            with zipped.open(info) as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target)
            temporary.replace(destination)
            members.append({
                "path": str(destination.relative_to(ROOT)),
                "bytes": destination.stat().st_size,
                "sha256": sha256(destination),
                "zip_crc32": f"{info.CRC:08x}",
            })

    csv_members = [member for member in members if member["path"].lower().endswith(".csv")]
    if len(csv_members) != 1:
        raise ValueError(f"Expected one flight CSV, found {len(csv_members)}")
    manifest = {
        "dataset": "BTS Reporting Carrier On-Time Performance (1987-present)",
        "publisher": "US Department of Transportation, Bureau of Transportation Statistics",
        "period": f"{year}-{month:02d}",
        "source_url": source_url,
        "source_directory_url": SOURCE_DIRECTORY,
        "field_definitions_url": FIELD_DEFINITIONS,
        "download_completed_at_utc": (
            previous["download_completed_at_utc"] if previous else
            datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc).isoformat()
        ),
        "download_timestamp_basis": "Archive last-write time on initial acquisition",
        "archive": {
            "path": str(archive.relative_to(ROOT)),
            "bytes": archive.stat().st_size,
            "sha256": archive_hash,
            "crc_integrity_check": "passed",
        },
        "members": members,
        "selection": "Complete monthly pre-zipped file; no fields or rows filtered",
        "raw_transformations": "None; archive members extracted byte-for-byte",
    }
    return manifest, manifest_path, ROOT / csv_members[0]["path"]


def read_definitions(readme_path):
    """Read the publisher's two-cell field-description table bundled in the ZIP."""
    content = readme_path.read_text(encoding="utf-8-sig")
    plain = lambda cell: " ".join(unescape(re.sub(r"<[^>]+>", "", cell)).split())
    definitions = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", content, flags=re.I | re.S):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)
        if len(cells) == 2:
            definitions[plain(cells[0])] = plain(cells[1])
    return definitions


def profile(csv_path, year, month):
    """Scan every record as text, preserving codes, time strings, and blanks."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        headers = next(reader)
        named_headers = [name for name in headers if name]
        if len(set(named_headers)) != len(named_headers):
            raise ValueError("CSV contains duplicate named columns")
        index = {name: position for position, name in enumerate(headers) if name}
        required = [
            "Year", "Month", "FlightDate", "Reporting_Airline", "Origin",
            "Dest", "Cancelled", "Diverted", "ArrDelay", "ArrDel15",
        ]
        missing = sorted(set(required) - index.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        blank_counts = [0] * len(headers)
        examples = [[] for _ in headers]
        dates = Counter()
        airlines = Counter()
        airports = set()
        routes = set()
        flags = {name: Counter() for name in ("Cancelled", "Diverted")}
        checks = Counter()
        rows = 0

        for row in reader:
            rows += 1
            if len(row) != len(headers):
                raise ValueError(f"Record {rows} has {len(row)} fields, expected {len(headers)}")
            for position, value in enumerate(row):
                if value == "":
                    blank_counts[position] += 1
                elif len(examples[position]) < 3 and value not in examples[position]:
                    examples[position].append(value)
            value = lambda name: row[index[name]]
            flight_date = date.fromisoformat(value("FlightDate")[:10])
            dates[flight_date.isoformat()] += 1
            if (flight_date.year, flight_date.month) != (year, month):
                checks["dates_outside_requested_month"] += 1
            if value("Year") != str(year) or int(value("Month")) != month:
                checks["year_month_field_mismatches"] += 1
            airlines[value("Reporting_Airline")] += 1
            airports.update((value("Origin"), value("Dest")))
            routes.add((value("Origin"), value("Dest")))
            for flag in flags:
                flags[flag][value(flag)] += 1
                if value(flag) not in {"0.00", "1.00", "0", "1", "0.0", "1.0"}:
                    checks["invalid_status_flags"] += 1
            cancelled = float(value("Cancelled")) == 1
            diverted = float(value("Diverted")) == 1
            checks["cancelled_and_diverted"] += int(cancelled and diverted)
            if value("ArrDelay") == "":
                checks["missing_arrival_delay"] += 1
                if not cancelled and not diverted:
                    checks["completed_nondiverted_missing_arrival_delay"] += 1
            if not cancelled and not diverted and value("ArrDelay") != "":
                checks["eligible_arrivals"] += 1
                if value("ArrDel15") == "" or float(value("ArrDel15")) != int(float(value("ArrDelay")) >= 15):
                    checks["arrival_delay_indicator_mismatches"] += 1

    if not rows:
        raise ValueError("CSV has no flight records")
    columns = [{
        "position": position + 1,
        "name": name or None,
        "blank_count": blank_counts[position],
        "blank_percent": round(100 * blank_counts[position] / rows, 4),
        "example_nonblank_values": examples[position],
        "read_type": "text; curated type to be defined during preparation",
    } for position, name in enumerate(headers)]
    return {
        "csv_path": str(csv_path.relative_to(ROOT)),
        "row_count": rows,
        "physical_column_count": len(headers),
        "named_column_count": len(named_headers),
        "columns": columns,
        "date_min": min(dates),
        "date_max": max(dates),
        "date_count": len(dates),
        "daily_row_counts": dict(sorted(dates.items())),
        "reporting_airline_counts": dict(sorted(airlines.items())),
        "distinct_airports_origin_or_destination": len(airports),
        "distinct_directional_routes": len(routes),
        "status_flag_counts": {name: dict(counts) for name, counts in flags.items()},
        "checks": {name: checks[name] for name in [
            "dates_outside_requested_month", "year_month_field_mismatches",
            "invalid_status_flags", "cancelled_and_diverted", "missing_arrival_delay",
            "completed_nondiverted_missing_arrival_delay", "eligible_arrivals",
            "arrival_delay_indicator_mismatches",
        ]},
        "inspection_scope": (
            "Full-file structure, blank counts, calendar coverage and status/target checks. "
            "Duplicate keys, complete type/range validation and lookup joins remain pending."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--month", type=int, choices=range(1, 13), default=1)
    args = parser.parse_args()
    date(args.year, args.month, 1)  # Validate before any network access.
    manifest, manifest_path, csv_path = acquire(args.year, args.month)
    print(f"Profiling {csv_path.name}", flush=True)
    result = profile(csv_path, args.year, args.month)
    profile_path = manifest_path.with_name(f"bts_{args.year}_{args.month:02d}_profile.json")
    definitions = read_definitions(csv_path.parent / "readme.html")
    dictionary = [{"name": column["name"], "source_description": definitions[column["name"]]}
                  for column in result["columns"] if column["name"]]
    dictionary_path = manifest_path.with_name(f"bts_{args.year}_{args.month:02d}_dictionary.json")
    manifest["row_count"] = result["row_count"]
    manifest["named_column_count"] = result["named_column_count"]
    manifest["profile_path"] = str(profile_path.relative_to(ROOT))
    manifest["dictionary_path"] = str(dictionary_path.relative_to(ROOT))
    write_json(dictionary_path, {
        "description_source": str((csv_path.parent / "readme.html").relative_to(ROOT)),
        "source_archive_url": manifest["source_url"],
        "fields": dictionary,
    })
    write_json(profile_path, result)
    write_json(manifest_path, manifest)
    print(json.dumps({
        "rows": result["row_count"], "named_columns": result["named_column_count"],
        "date_range": [result["date_min"], result["date_max"]],
        "checks": result["checks"], "manifest": str(manifest_path.relative_to(ROOT)),
    }, indent=2))


if __name__ == "__main__":
    main()
