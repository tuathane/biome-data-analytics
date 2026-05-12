# NOAA Tree-Ring Summaries

This repo contains a standalone Python script for downloading NOAA Paleo Search
tree-ring records and writing aggregate CSV summaries.

## Usage

```powershell
python .\tree_ring_summary.py --output-dir .\tree_ring_outputs
```

For a quick smoke test:

```powershell
python .\tree_ring_summary.py --max-studies 5 --output-dir .\tree_ring_outputs_sample
```

Small smoke tests often hit only raw-width studies. By default, growth CSVs use
NOAA chronology files when they are available and otherwise fall back to growth
derived from raw-width changes. You can force either behavior:

```powershell
python .\tree_ring_summary.py --growth-source chronology
python .\tree_ring_summary.py --growth-source width
```

The script uses the documented NOAA Paleo Search endpoint:

`https://www.ncei.noaa.gov/access/paleo-search/study/search.json`

It filters to `dataPublisher=NOAA` and `dataTypeId=18`, which NOAA's
`study/params.json` identifies as `TREE RING`.

## Outputs

The script writes:

- `tree_ring_growth_year_over_year.csv`
- `tree_ring_width_year_over_year.csv`
- `tree_ring_growth_decade_over_decade.csv`
- `tree_ring_width_decade_over_decade.csv`
- `tree_ring_growth_year_over_year_by_region.csv`
- `tree_ring_width_year_over_year_by_region.csv`
- `tree_ring_growth_decade_over_decade_by_region.csv`
- `tree_ring_width_decade_over_decade_by_region.csv`
- `manifest.json`

Each CSV includes `count`, `mean`, `median`, `stddev`, `mean_minus_stddev`, and
`mean_plus_stddev`.

Growth is computed as year-over-year or decade-over-decade change within the
same source series. With the default `--growth-source auto`, the script uses NOAA
chronology template files where the variable is `tree ring standardized growth
index` when chronology files are present. If none are present, it derives growth
from raw ring-width changes so small smoke tests still produce growth rows.

Width is computed from NOAA raw measurement template files where variables are
ring width measurements. Width files are summarized as measurement levels by
year and decade. Add `--include-earlywood-latewood` to include earlywood and
latewood width files when pure ring-width files are not available.

Region summaries use the NOAA `locationName` path. The default `--region-level 2`
turns a location such as `Continent>Europe>Western Europe>Switzerland` into
`Western Europe`.

## Visualizations

After aggregate CSVs have been written, install Plotly and pandas, then generate a separate
interactive HTML dashboard with:

```powershell
python -m pip install plotly pandas
python .\visualize_tree_ring_aggregates.py --input-dir .\tree_ring_outputs --output-dir .\tree_ring_visualizations
```

Open `tree_ring_visualizations\index.html` in a browser to view annual,
decadal, and regional Plotly charts. The charts support pan, wheel zoom, box
zoom, reset, year or decade range sliders, and legend-based region visibility
on the regional graphs. The visualization script is intentionally not called by
`tree_ring_summary.py`, so data collection and chart generation can be run
independently.
