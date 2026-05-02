#!/usr/bin/env python3
"""Visualize aggregate CSVs produced by tree_ring_summary.py.

This script is intentionally separate from the download/summarization run. It
uses only the Python standard library and writes a standalone HTML dashboard
with SVG charts.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_INPUT_DIR = "tree_ring_outputs"
DEFAULT_OUTPUT_DIR = "tree_ring_visualizations"


@dataclass(frozen=True)
class AggregateSpec:
    title: str
    filename: str
    period: str
    by_region: bool
    note: str


AGGREGATES = [
    AggregateSpec(
        "Annual Growth Change",
        "annual/tree_ring_growth_year_over_year.csv",
        "year",
        False,
        "Mean year-over-year change in the selected growth source.",
    ),
    AggregateSpec(
        "Annual Ring Width",
        "annual/tree_ring_width_year_over_year.csv",
        "year",
        False,
        "Mean raw ring-width measurement by year.",
    ),
    AggregateSpec(
        "Decadal Growth Change",
        "decade/tree_ring_growth_decade_over_decade.csv",
        "decade",
        False,
        "Mean decade-over-decade change in the selected growth source.",
    ),
    AggregateSpec(
        "Decadal Ring Width",
        "decade/tree_ring_width_decade_over_decade.csv",
        "decade",
        False,
        "Mean raw ring-width measurement by decade.",
    ),
    AggregateSpec(
        "Regional Annual Growth Change",
        "regional_annual/tree_ring_growth_year_over_year_by_region.csv",
        "year",
        True,
        "Top regions by observation count; each line is a regional mean.",
    ),
    AggregateSpec(
        "Regional Annual Ring Width",
        "regional_annual/tree_ring_width_year_over_year_by_region.csv",
        "year",
        True,
        "Top regions by observation count; each line is a regional mean.",
    ),
    AggregateSpec(
        "Regional Decadal Growth Change",
        "regional_decade/tree_ring_growth_decade_over_decade_by_region.csv",
        "decade",
        True,
        "Top regions by observation count; each line is a regional mean.",
    ),
    AggregateSpec(
        "Regional Decadal Ring Width",
        "regional_decade/tree_ring_width_decade_over_decade_by_region.csv",
        "decade",
        True,
        "Top regions by observation count; each line is a regional mean.",
    ),
]


PALETTE = [
    "#1f6f8b",
    "#b13f48",
    "#3f7f4f",
    "#9a6a16",
    "#6a5acd",
    "#c35f1d",
    "#008b8b",
    "#8b3a62",
    "#4f6f20",
    "#5f5f5f",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an HTML visualization dashboard from tree-ring aggregate CSV files."
    )
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="Directory containing aggregate CSV outputs.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for the HTML dashboard.")
    parser.add_argument(
        "--top-regions",
        type=int,
        default=8,
        help="Maximum number of regions to draw on each regional chart.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Skip aggregate rows whose count is below this value.",
    )
    return parser.parse_args()


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def to_int(value: str | None) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def read_csv(path: Path, period: str, min_count: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            period_value = to_int(raw.get(period))
            count = to_int(raw.get("count"))
            mean = to_float(raw.get("mean"))
            median = to_float(raw.get("median"))
            lower = to_float(raw.get("mean_minus_stddev"))
            upper = to_float(raw.get("mean_plus_stddev"))
            if period_value is None or count is None or mean is None or count < min_count:
                continue
            rows.append(
                {
                    period: period_value,
                    "region": raw.get("region", ""),
                    "count": count,
                    "mean": mean,
                    "median": median,
                    "lower": lower if lower is not None else mean,
                    "upper": upper if upper is not None else mean,
                }
            )
    return rows


def extent(values: Iterable[float]) -> tuple[float, float]:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return 0.0, 1.0
    low = min(clean)
    high = max(clean)
    if low == high:
        padding = abs(low) * 0.1 or 1.0
        return low - padding, high + padding
    padding = (high - low) * 0.06
    return low - padding, high + padding


def ticks(low: float, high: float, target: int = 6) -> list[float]:
    if high <= low:
        return [low]
    raw_step = (high - low) / max(target - 1, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    candidates = [1, 2, 5, 10]
    step = min(candidates, key=lambda c: abs(raw_step - c * magnitude)) * magnitude
    first = math.ceil(low / step) * step
    result = []
    value = first
    while value <= high + step * 0.5:
        result.append(value)
        value += step
    return result or [low, high]


def format_tick(value: float) -> str:
    if abs(value) >= 100 or value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def point_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    start = f"M {points[0][0]:.2f} {points[0][1]:.2f}"
    rest = " ".join(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
    return f"{start} {rest}".strip()


def chart_frame(
    rows: list[dict[str, Any]], period: str, value_keys: list[str]
) -> tuple[dict[str, float], Any, Any]:
    width = 920
    height = 360
    margin = {"left": 70, "right": 24, "top": 22, "bottom": 48}
    x_min, x_max = extent(float(row[period]) for row in rows)
    y_min, y_max = extent(float(row[key]) for row in rows for key in value_keys if row.get(key) is not None)

    def sx(value: float) -> float:
        span = x_max - x_min or 1.0
        return margin["left"] + ((value - x_min) / span) * (width - margin["left"] - margin["right"])

    def sy(value: float) -> float:
        span = y_max - y_min or 1.0
        return margin["top"] + (1 - ((value - y_min) / span)) * (height - margin["top"] - margin["bottom"])

    return (
        {
            "width": width,
            "height": height,
            "left": margin["left"],
            "right": margin["right"],
            "top": margin["top"],
            "bottom": margin["bottom"],
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
        },
        sx,
        sy,
    )


def axis_svg(frame: dict[str, float], sx: Any, sy: Any, period: str) -> str:
    width = frame["width"]
    height = frame["height"]
    left = frame["left"]
    right = frame["right"]
    top = frame["top"]
    bottom = frame["bottom"]
    plot_bottom = height - bottom
    plot_right = width - right
    x_ticks = ticks(frame["x_min"], frame["x_max"], 6)
    y_ticks = ticks(frame["y_min"], frame["y_max"], 6)
    parts = [
        f'<line class="axis" x1="{left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" />',
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{plot_bottom}" />',
    ]
    for value in y_ticks:
        y = sy(value)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.2f}" x2="{plot_right}" y2="{y:.2f}" />')
        parts.append(f'<text class="tick ytick" x="{left - 10}" y="{y + 4:.2f}">{format_tick(value)}</text>')
    for value in x_ticks:
        x = sx(value)
        parts.append(f'<line class="tickline" x1="{x:.2f}" y1="{plot_bottom}" x2="{x:.2f}" y2="{plot_bottom + 5}" />')
        parts.append(f'<text class="tick xtick" x="{x:.2f}" y="{plot_bottom + 24}">{format_tick(value)}</text>')
    parts.append(f'<text class="axis-label" x="{(left + plot_right) / 2:.2f}" y="{height - 8}">{period.title()}</text>')
    return "\n".join(parts)


def single_series_chart(rows: list[dict[str, Any]], period: str) -> str:
    if not rows:
        return '<div class="empty">No rows available.</div>'
    rows = sorted(rows, key=lambda row: row[period])
    frame, sx, sy = chart_frame(rows, period, ["mean", "lower", "upper"])
    mean_points = [(sx(row[period]), sy(row["mean"])) for row in rows]
    median_points = [
        (sx(row[period]), sy(row["median"])) for row in rows if row.get("median") is not None
    ]
    upper_points = [(sx(row[period]), sy(row["upper"])) for row in rows]
    lower_points = [(sx(row[period]), sy(row["lower"])) for row in reversed(rows)]
    band_path = f"{point_path(upper_points)} {point_path(lower_points).replace('M', 'L', 1)} Z"
    count_total = sum(row["count"] for row in rows)
    period_min = rows[0][period]
    period_max = rows[-1][period]
    return f"""
<svg class="chart" viewBox="0 0 {frame['width']} {frame['height']}" role="img">
  {axis_svg(frame, sx, sy, period)}
  <path class="band" d="{band_path}" />
  <path class="line primary" d="{point_path(mean_points)}" />
  <path class="line median" d="{point_path(median_points)}" />
</svg>
<div class="meta">{len(rows):,} periods, {count_total:,} observations, {period_min} to {period_max}</div>
"""


def region_totals(rows: list[dict[str, Any]]) -> list[tuple[str, int, int]]:
    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        region = str(row.get("region") or "Unknown")
        item = totals.setdefault(region, {"count": 0, "periods": 0})
        item["count"] += int(row["count"])
        item["periods"] += 1
    return sorted(
        ((region, values["count"], values["periods"]) for region, values in totals.items()),
        key=lambda item: (-item[1], item[0]),
    )


def regional_chart(rows: list[dict[str, Any]], period: str, top_regions: int) -> str:
    if not rows:
        return '<div class="empty">No rows available.</div>'
    selected_regions = [region for region, _count, _periods in region_totals(rows)[:top_regions]]
    selected = [row for row in rows if row.get("region") in selected_regions]
    frame, sx, sy = chart_frame(selected, period, ["mean"])
    parts = [
        f'<svg class="chart" viewBox="0 0 {frame["width"]} {frame["height"]}" role="img">',
        axis_svg(frame, sx, sy, period),
    ]
    legend = []
    for index, region in enumerate(selected_regions):
        color = PALETTE[index % len(PALETTE)]
        region_rows = sorted((row for row in selected if row.get("region") == region), key=lambda row: row[period])
        path = point_path([(sx(row[period]), sy(row["mean"])) for row in region_rows])
        parts.append(f'<path class="line region-line" style="stroke:{color}" d="{path}" />')
        legend.append(
            f'<span class="legend-item"><span class="swatch" style="background:{color}"></span>{html.escape(region)}</span>'
        )
    parts.append("</svg>")
    coverage_rows = "\n".join(
        f"<tr><td>{html.escape(region)}</td><td>{count:,}</td><td>{periods:,}</td></tr>"
        for region, count, periods in region_totals(rows)[:top_regions]
    )
    return f"""
{''.join(parts)}
<div class="legend">{''.join(legend)}</div>
<table class="coverage">
  <thead><tr><th>Region</th><th>Observations</th><th>Periods</th></tr></thead>
  <tbody>{coverage_rows}</tbody>
</table>
"""


def manifest_summary(input_dir: Path) -> str:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.exists():
        return "No manifest.json found."
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "manifest.json could not be parsed."
    parts = []
    for key in ("processed_studies", "resolved_growth_source", "growth_source"):
        if key in manifest:
            parts.append(f"{key.replace('_', ' ')}: {manifest[key]}")
    if "growth_files" in manifest:
        parts.append(f"growth files: {len(manifest['growth_files'])}")
    if "width_files" in manifest:
        parts.append(f"width files: {len(manifest['width_files'])}")
    if "errors" in manifest:
        parts.append(f"errors: {len(manifest['errors'])}")
    return "; ".join(parts) if parts else "Manifest found."


def render_dashboard(input_dir: Path, output_dir: Path, top_regions: int, min_count: int) -> Path:
    sections = []
    for spec in AGGREGATES:
        path = input_dir / spec.filename
        rows = read_csv(path, spec.period, min_count)
        chart = (
            regional_chart(rows, spec.period, top_regions)
            if spec.by_region
            else single_series_chart(rows, spec.period)
        )
        sections.append(
            f"""
<section>
  <div class="section-heading">
    <h2>{html.escape(spec.title)}</h2>
    <p>{html.escape(spec.note)}</p>
    <code>{html.escape(spec.filename)}</code>
  </div>
  {chart}
</section>
"""
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "index.html"
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NOAA Tree-Ring Aggregate Visualizations</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8f4;
      --ink: #20242a;
      --muted: #5e6875;
      --panel: #ffffff;
      --rule: #d9ded6;
      --grid: #e7ebe4;
      --accent: #1f6f8b;
      --accent-soft: #cfe2e8;
      --median: #8f3f46;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    header, main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    header {{ padding-top: 34px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(1.8rem, 3vw, 2.8rem); letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 1.25rem; letter-spacing: 0; }}
    p {{ margin: 6px 0 0; color: var(--muted); }}
    code {{
      display: inline-block;
      margin-top: 8px;
      padding: 3px 6px;
      border: 1px solid var(--rule);
      border-radius: 4px;
      background: #f1f3ef;
      color: #39404a;
      font-size: 0.86rem;
    }}
    section {{
      margin: 0 0 24px;
      padding: 20px;
      background: var(--panel);
      border: 1px solid var(--rule);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(32, 36, 42, 0.04);
    }}
    .section-heading {{ margin-bottom: 12px; }}
    .chart {{ width: 100%; height: auto; display: block; }}
    .axis, .tickline {{ stroke: #8b949e; stroke-width: 1; }}
    .grid {{ stroke: var(--grid); stroke-width: 1; }}
    .tick, .axis-label {{ fill: #586270; font-size: 12px; }}
    .ytick {{ text-anchor: end; }}
    .xtick, .axis-label {{ text-anchor: middle; }}
    .band {{ fill: var(--accent-soft); opacity: 0.72; }}
    .line {{ fill: none; stroke-width: 2.1; stroke-linejoin: round; stroke-linecap: round; }}
    .primary {{ stroke: var(--accent); }}
    .median {{ stroke: var(--median); stroke-width: 1.5; stroke-dasharray: 5 5; }}
    .region-line {{ opacity: 0.9; }}
    .meta, .legend {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 8px 14px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
    .swatch {{ width: 12px; height: 12px; border-radius: 3px; display: inline-block; }}
    .coverage {{
      width: 100%;
      margin-top: 12px;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    .coverage th, .coverage td {{
      padding: 7px 8px;
      border-top: 1px solid var(--rule);
      text-align: right;
    }}
    .coverage th:first-child, .coverage td:first-child {{ text-align: left; }}
    .empty {{
      padding: 18px;
      border: 1px dashed var(--rule);
      border-radius: 6px;
      color: var(--muted);
      background: #fbfcfa;
    }}
  </style>
</head>
<body>
  <header>
    <h1>NOAA Tree-Ring Aggregate Visualizations</h1>
    <p>{html.escape(manifest_summary(input_dir))}</p>
  </header>
  <main>
    {''.join(sections)}
  </main>
</body>
</html>
"""
    output_path.write_text(document, encoding="utf-8")
    return output_path


def main() -> int:
    args = parse_args()
    output_path = render_dashboard(
        Path(args.input_dir),
        Path(args.output_dir),
        max(args.top_regions, 1),
        max(args.min_count, 1),
    )
    print(f"Wrote visualization dashboard to {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
