#!/usr/bin/env python3
"""Create interactive Plotly charts from tree-ring aggregate CSVs.

This script is intentionally separate from tree_ring_summary.py. Run the summary
script first, then run this script whenever you want to rebuild the dashboard.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        "Top regions by observation count are visible by default. Use the legend to show or hide regions.",
    ),
    AggregateSpec(
        "Regional Annual Ring Width",
        "regional_annual/tree_ring_width_year_over_year_by_region.csv",
        "year",
        True,
        "Top regions by observation count are visible by default. Use the legend to show or hide regions.",
    ),
    AggregateSpec(
        "Regional Decadal Growth Change",
        "regional_decade/tree_ring_growth_decade_over_decade_by_region.csv",
        "decade",
        True,
        "Top regions by observation count are visible by default. Use the legend to show or hide regions.",
    ),
    AggregateSpec(
        "Regional Decadal Ring Width",
        "regional_decade/tree_ring_width_decade_over_decade_by_region.csv",
        "decade",
        True,
        "Top regions by observation count are visible by default. Use the legend to show or hide regions.",
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
    "#7a4f2a",
    "#2f5597",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an interactive Plotly dashboard from tree-ring aggregate CSV files."
    )
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="Directory containing aggregate CSV outputs.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for the HTML dashboard.")
    parser.add_argument(
        "--top-regions",
        type=int,
        default=8,
        help="Number of highest-observation regions shown by default on regional charts.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Skip aggregate rows whose count is below this value.",
    )
    return parser.parse_args()


def require_plotting() -> dict[str, Any]:
    missing: list[str] = []
    try:
        import pandas as pd
    except ModuleNotFoundError:
        missing.append("pandas")
        pd = None
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ModuleNotFoundError:
        missing.append("plotly")
        go = None
        pio = None
    if missing:
        packages = " ".join(missing)
        print(
            "Plotly and pandas are required for interactive visualizations. Install them with:\n\n"
            f"    python -m pip install {packages}\n",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return {"pd": pd, "go": go, "pio": pio}


def read_csv(pd: Any, path: Path, period: str, min_count: int) -> Any:
    columns = ["period", "region", "count", "mean", "median", "lower", "upper"]
    if not path.exists():
        return pd.DataFrame(columns=columns)

    frame = pd.read_csv(path)
    if period not in frame.columns or "count" not in frame.columns or "mean" not in frame.columns:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame()
    result["period"] = pd.to_numeric(frame[period], errors="coerce")
    result["count"] = pd.to_numeric(frame["count"], errors="coerce")
    result["mean"] = pd.to_numeric(frame["mean"], errors="coerce")

    if "region" in frame.columns:
        result["region"] = frame["region"].fillna("All").astype(str).replace("", "All")
    else:
        result["region"] = "All"

    for output_name, input_name in (
        ("median", "median"),
        ("lower", "mean_minus_stddev"),
        ("upper", "mean_plus_stddev"),
    ):
        if input_name in frame.columns:
            result[output_name] = pd.to_numeric(frame[input_name], errors="coerce")
        else:
            result[output_name] = math.nan

    result = result.dropna(subset=["period", "count", "mean"])
    result = result[result["count"] >= min_count].copy()
    result["period"] = result["period"].astype(int)
    result["count"] = result["count"].astype(int)
    result["median"] = result["median"].fillna(result["mean"])
    result["lower"] = result["lower"].fillna(result["mean"])
    result["upper"] = result["upper"].fillna(result["mean"])
    return result[columns].sort_values(["region", "period"])


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


def region_order(frame: Any) -> list[str]:
    totals = frame.groupby("region", dropna=False).agg(count=("count", "sum")).reset_index()
    totals = totals.sort_values(["count", "region"], ascending=[False, True])
    return [str(region) for region in totals["region"].tolist()]


def apply_common_layout(fig: Any, spec: AggregateSpec, period_title: str) -> None:
    fig.update_layout(
        title=None,
        height=430,
        margin={"l": 58, "r": 24, "t": 18, "b": 48},
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="closest",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 12},
        },
        font={"family": "Arial, Helvetica, sans-serif", "color": "#20242a"},
    )
    fig.update_xaxes(
        title=period_title,
        showgrid=True,
        gridcolor="#e7ebe4",
        zeroline=False,
        rangeslider={"visible": True, "thickness": 0.08},
    )
    fig.update_yaxes(title="Mean", showgrid=True, gridcolor="#e7ebe4", zeroline=False)


def single_series_figure(go: Any, spec: AggregateSpec, frame: Any) -> Any:
    period_title = spec.period.title()
    frame = frame.sort_values("period")
    fig = go.Figure()
    band_x = list(frame["period"]) + list(reversed(frame["period"]))
    band_y = list(frame["upper"]) + list(reversed(frame["lower"]))
    fig.add_trace(
        go.Scatter(
            x=band_x,
            y=band_y,
            fill="toself",
            fillcolor="rgba(31, 111, 139, 0.18)",
            line={"color": "rgba(31, 111, 139, 0)"},
            hoverinfo="skip",
            name="Mean +/- stddev",
            showlegend=True,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["period"],
            y=frame["mean"],
            mode="lines+markers",
            name="Mean",
            line={"color": PALETTE[0], "width": 2.4},
            marker={"size": 5},
            customdata=frame[["median", "count", "lower", "upper"]],
            hovertemplate=(
                f"{period_title}: %{{x}}<br>"
                "Mean: %{y:.4f}<br>"
                "Median: %{customdata[0]:.4f}<br>"
                "Count: %{customdata[1]:,}<br>"
                "Mean - stddev: %{customdata[2]:.4f}<br>"
                "Mean + stddev: %{customdata[3]:.4f}<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["period"],
            y=frame["median"],
            mode="lines",
            name="Median",
            line={"color": "#8f3f46", "width": 1.8, "dash": "dash"},
            customdata=frame[["mean", "count"]],
            hovertemplate=(
                f"{period_title}: %{{x}}<br>"
                "Median: %{y:.4f}<br>"
                "Mean: %{customdata[0]:.4f}<br>"
                "Count: %{customdata[1]:,}<extra></extra>"
            ),
        )
    )
    apply_common_layout(fig, spec, period_title)
    return fig


def regional_figure(go: Any, spec: AggregateSpec, frame: Any, top_regions: int) -> Any:
    period_title = spec.period.title()
    ordered_regions = region_order(frame)
    visible_regions = set(ordered_regions[: max(top_regions, 1)])
    fig = go.Figure()

    for index, region in enumerate(ordered_regions):
        region_frame = frame[frame["region"] == region].sort_values("period")
        visible = True if region in visible_regions else "legendonly"
        fig.add_trace(
            go.Scatter(
                x=region_frame["period"],
                y=region_frame["mean"],
                mode="lines+markers",
                name=str(region),
                visible=visible,
                line={"color": PALETTE[index % len(PALETTE)], "width": 2.2},
                marker={"size": 5},
                customdata=region_frame[["count"]],
                hovertemplate=(
                    f"Region: {html.escape(str(region))}<br>"
                    f"{period_title}: %{{x}}<br>"
                    "Mean: %{y:.4f}<br>"
                    "Count: %{customdata[0]:,}<extra></extra>"
                ),
            )
        )

    apply_common_layout(fig, spec, period_title)
    fig.update_layout(
        legend={
            "orientation": "v",
            "yanchor": "top",
            "y": 1,
            "xanchor": "left",
            "x": 1.01,
            "font": {"size": 11},
            "itemsizing": "constant",
        },
        margin={"l": 58, "r": 210, "t": 18, "b": 48},
    )
    return fig


def section_html(pio: Any, spec: AggregateSpec, row_count: int, figure: Any | None, include_plotlyjs: bool) -> str:
    chart = '<div class="empty">No rows available.</div>'
    if figure is not None:
        chart = pio.to_html(
            figure,
            include_plotlyjs=True if include_plotlyjs else False,
            full_html=False,
            config={"responsive": True, "displaylogo": False, "scrollZoom": True},
        )
    return f"""
<section>
  <div class="section-heading">
    <h2>{html.escape(spec.title)}</h2>
    <p>{html.escape(spec.note)}</p>
    <code>{html.escape(spec.filename)}</code>
    <p class="meta">{row_count:,} aggregate rows loaded.</p>
  </div>
  {chart}
</section>
"""


def page_html(title: str, manifest: str, sections: list[str]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #f7f8f4;
      color: #20242a;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    header, main {{
      width: min(1180px, calc(100vw - 36px));
      margin: 0 auto;
    }}
    header {{ padding: 32px 0 10px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 20px; letter-spacing: 0; }}
    p {{ margin: 6px 0 0; color: #5e6875; }}
    code {{
      display: inline-block;
      margin-top: 8px;
      padding: 3px 6px;
      border: 1px solid #d9ded6;
      border-radius: 4px;
      background: #f1f3ef;
      color: #39404a;
      font-size: 13px;
    }}
    section {{
      margin: 18px 0 24px;
      padding: 16px 18px 10px;
      background: white;
      border: 1px solid #d9ded6;
      border-radius: 8px;
    }}
    .section-heading {{ margin-bottom: 8px; }}
    .meta {{ font-size: 13px; }}
    .empty {{
      padding: 18px;
      border: 1px dashed #d9ded6;
      border-radius: 6px;
      color: #5e6875;
      background: #fbfcfa;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(manifest)}</p>
  </header>
  <main>
    {''.join(sections)}
  </main>
</body>
</html>
"""


def render_dashboard(input_dir: Path, output_dir: Path, top_regions: int, min_count: int) -> Path:
    libs = require_plotting()
    pd = libs["pd"]
    go = libs["go"]
    pio = libs["pio"]

    sections: list[str] = []
    include_plotlyjs = True
    for spec in AGGREGATES:
        frame = read_csv(pd, input_dir / spec.filename, spec.period, min_count)
        figure = None
        if not frame.empty:
            if spec.by_region:
                figure = regional_figure(go, spec, frame, top_regions)
            else:
                figure = single_series_figure(go, spec, frame)
        sections.append(section_html(pio, spec, len(frame), figure, include_plotlyjs and figure is not None))
        if figure is not None:
            include_plotlyjs = False

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "index.html"
    output_path.write_text(
        page_html("NOAA Tree-Ring Aggregate Visualizations", manifest_summary(input_dir), sections),
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    args = parse_args()
    output_path = render_dashboard(
        Path(args.input_dir),
        Path(args.output_dir),
        max(args.top_regions, 1),
        max(args.min_count, 1),
    )
    print(f"Wrote interactive Plotly dashboard to {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
