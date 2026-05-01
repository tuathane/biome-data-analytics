#!/usr/bin/env python3
"""Fetch NOAA Paleo Search tree-ring records and summarize growth/width trends."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


API_BASE = "https://www.ncei.noaa.gov/access/paleo-search/study/search.json"
TREE_RING_DATA_TYPE_ID = "18"
USER_AGENT = "biome-data-analytics-tree-ring-summary/0.00.0001"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download NOAA Paleo Search tree-ring metadata/data files and write "
            "year-over-year and decade-over-decade aggregate CSV summaries."
        )
    )
    parser.add_argument("--output-dir", default="tree_ring_outputs")
    parser.add_argument("--limit", type=int, default=100, help="API page size.")
    parser.add_argument("--skip", type=int, default=0, help="Initial API offset.")
    parser.add_argument(
        "--max-studies",
        type=int,
        default=None,
        help="Optional cap for testing; omit to process all NOAA tree-ring studies.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.15,
        help="Seconds to pause between NOAA requests.",
    )
    parser.add_argument(
        "--region-level",
        type=int,
        default=2,
        help=(
            "Zero-based component of NOAA locationName to use as region. "
            "Example: Continent>Europe>Western Europe>Switzerland -> level 2 is Western Europe."
        ),
    )
    parser.add_argument(
        "--include-earlywood-latewood",
        action="store_true",
        help="Include earlywood/latewood width files when pure ring width files are absent.",
    )
    return parser.parse_args()


def get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_studies(limit: int, skip: int, max_studies: int | None, sleep: float) -> Iterable[dict[str, Any]]:
    yielded = 0
    offset = skip
    while True:
        page_limit = limit
        if max_studies is not None:
            remaining = max_studies - yielded
            if remaining <= 0:
                return
            page_limit = min(page_limit, remaining)

        data = get_json(
            API_BASE,
            {
                "dataPublisher": "NOAA",
                "dataTypeId": TREE_RING_DATA_TYPE_ID,
                "reconstructionsOnly": "N",
                "limit": page_limit,
                "skip": offset,
            },
        )
        studies = data.get("study", [])
        if not studies:
            return

        for study in studies:
            yield study
            yielded += 1
            if max_studies is not None and yielded >= max_studies:
                return

        if len(studies) < page_limit:
            return
        offset += len(studies)
        time.sleep(sleep)


def flatten_data_files(study: dict[str, Any]) -> Iterable[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    for site in study.get("site", []) or []:
        for table in site.get("paleoData", []) or []:
            for data_file in table.get("dataFile", []) or []:
                yield site, table, data_file


def variable_text(data_file: dict[str, Any]) -> str:
    parts: list[str] = []
    for var in data_file.get("variables", []) or []:
        for key in ("cvWhat", "cvUnit", "cvDetail", "cvMethod", "cvAdditionalInfo", "cvShortName"):
            value = var.get(key)
            if value:
                parts.append(str(value))
    parts.extend(data_file.get("NOAAKeywords", []) or [])
    parts.append(str(data_file.get("urlDescription", "")))
    parts.append(str(data_file.get("linkText", "")))
    return " | ".join(parts).lower()


def is_noaa_template(data_file: dict[str, Any]) -> bool:
    return "noaa" in str(data_file.get("urlDescription", "")).lower() or "-noaa" in str(
        data_file.get("fileUrl", "")
    ).lower()


def is_growth_file(data_file: dict[str, Any]) -> bool:
    text = variable_text(data_file)
    non_ring_width_terms = ("earlywood", "latewood", "density")
    return (
        is_noaa_template(data_file)
        and "chronology" in str(data_file.get("urlDescription", "")).lower()
        and "tree ring standardized growth index" in text
        and "residual chronology method" not in text
        and "arstan chronology method" not in text
        and not any(term in text for term in non_ring_width_terms)
    )


def is_width_file(data_file: dict[str, Any], include_earlywood_latewood: bool) -> bool:
    text = variable_text(data_file)
    if not is_noaa_template(data_file):
        return False
    if "raw measurements" not in str(data_file.get("urlDescription", "")).lower():
        return False
    if "physical property>width>ring width" in text or "physical property>width>total ring width" in text:
        return True
    return include_earlywood_latewood and (
        "physical property>width>earlywood width" in text
        or "physical property>width>latewood width" in text
    )


def region_from_site(site: dict[str, Any], level: int) -> str:
    location = site.get("locationName") or "Unknown"
    parts = [part.strip() for part in str(location).split(">") if part.strip()]
    if 0 <= level < len(parts):
        return parts[level]
    return parts[-1] if parts else "Unknown"


def parse_template_table(text: str) -> tuple[list[str], list[dict[str, str]]]:
    data_lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not data_lines:
        return [], []
    delimiter = "\t" if "\t" in data_lines[0] else ","
    reader = csv.DictReader(data_lines, delimiter=delimiter)
    return reader.fieldnames or [], list(reader)


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.upper() in {"NA", "NAN", "NULL"}:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def age_column(fieldnames: list[str]) -> str | None:
    for name in fieldnames:
        lowered = name.lower()
        if lowered in {"age_ce", "year", "yyyy"} or "age" in lowered:
            return name
    return fieldnames[0] if fieldnames else None


def extract_growth_points(
    rows: list[dict[str, str]], fieldnames: list[str], source: str, region: str
) -> list[dict[str, Any]]:
    age_col = age_column(fieldnames)
    if not age_col:
        return []
    value_cols = [name for name in fieldnames if name.lower() in {"trsgi", "rwi", "std"}]
    if not value_cols:
        value_cols = [
            name
            for name in fieldnames
            if name != age_col and "samp" not in name.lower() and "depth" not in name.lower()
        ][:1]

    points: list[dict[str, Any]] = []
    for row in rows:
        year_value = to_float(row.get(age_col))
        if year_value is None:
            continue
        year = int(year_value)
        for col in value_cols:
            value = to_float(row.get(col))
            if value is not None:
                points.append({"source": source, "series": col, "region": region, "year": year, "value": value})
    return points


def extract_width_points(
    rows: list[dict[str, str]], fieldnames: list[str], source: str, region: str
) -> list[dict[str, Any]]:
    age_col = age_column(fieldnames)
    if not age_col:
        return []
    value_cols = [
        name
        for name in fieldnames
        if name != age_col
        and "raw" in name.lower()
        and "samp" not in name.lower()
        and "depth" not in name.lower()
    ]
    if not value_cols:
        value_cols = [
            name
            for name in fieldnames
            if name != age_col and "samp" not in name.lower() and "depth" not in name.lower()
        ]

    points: list[dict[str, Any]] = []
    for row in rows:
        year_value = to_float(row.get(age_col))
        if year_value is None:
            continue
        year = int(year_value)
        for col in value_cols:
            value = to_float(row.get(col))
            if value is not None:
                points.append({"source": source, "series": col, "region": region, "year": year, "value": value})
    return points


def summarize_values(values: list[float]) -> dict[str, Any]:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return {}
    mean = statistics.fmean(clean)
    stddev = statistics.stdev(clean) if len(clean) > 1 else 0.0
    return {
        "count": len(clean),
        "mean": mean,
        "median": statistics.median(clean),
        "stddev": stddev,
        "mean_minus_stddev": mean - stddev,
        "mean_plus_stddev": mean + stddev,
    }


def decade_for_year(year: int) -> int:
    return (year // 10) * 10


def aggregate_levels(points: list[dict[str, Any]], period: str, by_region: bool) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    for point in points:
        bucket = point["year"] if period == "year" else decade_for_year(point["year"])
        key = (point["region"], bucket) if by_region else (bucket,)
        grouped[key].append(point["value"])

    rows: list[dict[str, Any]] = []
    for key, values in sorted(grouped.items()):
        stats = summarize_values(values)
        if not stats:
            continue
        row: dict[str, Any] = {}
        if by_region:
            row["region"] = key[0]
            row[period] = key[1]
        else:
            row[period] = key[0]
        row.update(stats)
        rows.append(row)
    return rows


def aggregate_changes(points: list[dict[str, Any]], period: str, by_region: bool) -> list[dict[str, Any]]:
    series_values: dict[tuple[str, str, str], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for point in points:
        bucket = point["year"] if period == "year" else decade_for_year(point["year"])
        series_key = (point["source"], point["series"], point["region"])
        series_values[series_key][bucket].append(point["value"])

    changes: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    for (_source, _series, region), bucket_values in series_values.items():
        collapsed = {bucket: statistics.fmean(values) for bucket, values in bucket_values.items()}
        buckets = sorted(collapsed)
        for previous, current in zip(buckets, buckets[1:]):
            expected_step = 1 if period == "year" else 10
            if current - previous != expected_step:
                continue
            change = collapsed[current] - collapsed[previous]
            key = (region, current) if by_region else (current,)
            changes[key].append(change)

    rows: list[dict[str, Any]] = []
    for key, values in sorted(changes.items()):
        stats = summarize_values(values)
        if not stats:
            continue
        row: dict[str, Any] = {}
        if by_region:
            row["region"] = key[0]
            row[period] = key[1]
        else:
            row[period] = key[0]
        row.update(stats)
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], first_columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = first_columns + ["count", "mean", "median", "stddev", "mean_minus_stddev", "mean_plus_stddev"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    growth_points: list[dict[str, Any]] = []
    width_points: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "api": API_BASE,
        "dataPublisher": "NOAA",
        "dataTypeId": TREE_RING_DATA_TYPE_ID,
        "reconstructionsOnly": "N",
        "processed_studies": 0,
        "growth_files": [],
        "width_files": [],
        "errors": [],
    }

    for study in fetch_studies(args.limit, args.skip, args.max_studies, args.sleep):
        manifest["processed_studies"] += 1
        study_id = study.get("NOAAStudyId") or study.get("xmlId")
        for site, _table, data_file in flatten_data_files(study):
            file_url = data_file.get("fileUrl")
            if not file_url:
                continue
            region = region_from_site(site, args.region_level)
            source = f"{study_id}:{data_file.get('linkText') or Path(urllib.parse.urlparse(file_url).path).name}"
            try:
                if is_growth_file(data_file):
                    text = get_text(file_url)
                    fields, rows = parse_template_table(text)
                    points = extract_growth_points(rows, fields, source, region)
                    growth_points.extend(points)
                    manifest["growth_files"].append({"study": study_id, "url": file_url, "points": len(points)})
                    time.sleep(args.sleep)
                elif is_width_file(data_file, args.include_earlywood_latewood):
                    text = get_text(file_url)
                    fields, rows = parse_template_table(text)
                    points = extract_width_points(rows, fields, source, region)
                    width_points.extend(points)
                    manifest["width_files"].append({"study": study_id, "url": file_url, "points": len(points)})
                    time.sleep(args.sleep)
            except (urllib.error.URLError, TimeoutError, UnicodeError, csv.Error) as exc:
                manifest["errors"].append({"study": study_id, "url": file_url, "error": str(exc)})
                print(f"warning: skipped {file_url}: {exc}", file=sys.stderr)

    write_csv(
        output_dir / "annual" / "tree_ring_growth_year_over_year.csv",
        aggregate_changes(growth_points, "year", by_region=False),
        ["year"],
    )
    write_csv(
        output_dir / "annual" / "tree_ring_width_year_over_year.csv",
        aggregate_levels(width_points, "year", by_region=False),
        ["year"],
    )
    write_csv(
        output_dir / "decade" / "tree_ring_growth_decade_over_decade.csv",
        aggregate_changes(growth_points, "decade", by_region=False),
        ["decade"],
    )
    write_csv(
        output_dir / "decade" / "tree_ring_width_decade_over_decade.csv",
        aggregate_levels(width_points, "decade", by_region=False),
        ["decade"],
    )
    write_csv(
        output_dir / "regional_annual" / "tree_ring_growth_year_over_year_by_region.csv",
        aggregate_changes(growth_points, "year", by_region=True),
        ["region", "year"],
    )
    write_csv(
        output_dir / "regional_annual" / "tree_ring_width_year_over_year_by_region.csv",
        aggregate_levels(width_points, "year", by_region=True),
        ["region", "year"],
    )
    write_csv(
        output_dir / "regional_decade" / "tree_ring_growth_decade_over_decade_by_region.csv",
        aggregate_changes(growth_points, "decade", by_region=True),
        ["region", "decade"],
    )
    write_csv(
        output_dir / "regional_decade" / "tree_ring_width_decade_over_decade_by_region.csv",
        aggregate_levels(width_points, "decade", by_region=True),
        ["region", "decade"],
    )
    write_manifest(output_dir / "manifest.json", manifest)

    print(f"Processed {manifest['processed_studies']} studies")
    print(f"Parsed {len(manifest['growth_files'])} growth files and {len(manifest['width_files'])} width files")
    print(f"Wrote outputs to {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
