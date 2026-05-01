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

Growth is computed from NOAA chronology template files where the variable is
`tree ring standardized growth index`, reconstructed from ring width, using the
standard chronology method. Year-over-year and decade-over-decade growth values
are changes from the previous contiguous year or decade within the same source
series.

Width is computed from NOAA raw measurement template files where variables are
ring width measurements. Width files are summarized as measurement levels by
year and decade. Add `--include-earlywood-latewood` to include earlywood and
latewood width files when pure ring-width files are not available.

Region summaries use the NOAA `locationName` path. The default `--region-level 2`
turns a location such as `Continent>Europe>Western Europe>Switzerland` into
`Western Europe`.
