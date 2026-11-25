# Reproducing the calculations

[← README](../README.md)

## 1. Recompute the archived results

From the repository root, with Python 3.11 or later:

```sh
python run_analysis.py --check-models
python -m unittest discover -s tests -v
```

No EnergyPlus installation or third-party Python package is needed for this step.
The monthly zone records in `data/monthly_zone_loads.csv` are summed and divided
by the actual conditioned area of each model. Annual values are checked against
`data/annual_results.csv`.

Output files in `outputs/analysis/`:

| File | Contents |
| --- | --- |
| `annual_results.csv` | Recomputed heating, cooling and combined demand with case metadata |
| `pairwise_comparisons.csv` | Six prototype pairs × three metrics for every common sensitivity condition |
| `factorial_contrasts.csv` | Main high-minus-low contrasts, averaged two-way differences and three-way differences |
| `summary.json` | Counts of conditions with reversals and near-ties, plus verification results |

`run_analysis.py` can overwrite its generated outputs. Model generation,
simulation and single-run extraction require a new output directory to preserve
previous runs.

## 2. Generate figures and baseline models

```sh
python -m pip install -r requirements.txt
python run_analysis.py --figures
python build_models.py --out outputs/rebuilt-models
```

The builder uses Shapely 2.1.2, a 1 mm geometry grid and the supplied floor
polygons. It checks floor and roof areas, wall perimeters, paired surfaces and
window-to-wall ratios before writing IDFs. All generated EnergyPlus objects must
match the archived baseline objects; comments and whitespace are ignored in
that comparison.

The archived sensitivity IDFs are supplied directly in `models/`. This release
regenerates the four baseline models; it does not regenerate every historical
geometry-branch and parameter-editing script.

## 3. Rerun EnergyPlus

Install the [EnergyPlus 26.1.0 release](https://github.com/NatLabRockies/EnergyPlus/releases/tag/v26.1.0).
The archived build is `26.1.0-6f2e40d102`. Obtain the
[Taiyuan CSWD weather archive](https://energyplus-weather.s3.amazonaws.com/asia_wmo_region_2/CHN/CHN_Shanxi.Taiyuan.537720_CSWD/CHN_Shanxi.Taiyuan.537720_CSWD.zip)
and extract `CHN_Shanxi.Taiyuan.537720_CSWD.epw`.
The executable and weather-file checksum are checked before any run starts.

Replace the two example paths below with local paths. The same command syntax
works in PowerShell and POSIX shells when entered on one line:

```sh
python run_simulations.py --energyplus "/path/to/energyplus" --weather "/path/to/CHN_Shanxi.Taiyuan.537720_CSWD.epw" --group baseline --jobs 2 --out outputs/baseline-rerun
```

On Windows, the executable normally ends in `energyplus.exe`. Keep its adjacent
`Energy+.idd` and other installed runtime files in place.

| `--group` | Number of runs |
| --- | ---: |
| `baseline` | 4 |
| `geometry` | 6 |
| `ofat` | 64 |
| `factorial` | 96 |
| `all` | 170 |

Every case receives its own directory containing the engine outputs, stdout and
extracted monthly data. `run_summary.json` records completion, hashes and the
maximum metric difference from the archive. An unsuccessful or incomplete run
causes the command to exit with an error after recording the other results.

All 170 original SQL files total about **3.2 GB**. The repository distributes
compact monthly data instead of these full databases. Rerunning creates fresh
SQL files; byte hashes may differ because the databases include runtime metadata.
Compare the numerical metrics, and inspect the `.err` files.

## 4. Extract one completed run

```sh
python extract_results.py --sql outputs/baseline-rerun/R_M03_horizontal/eplusout.sql --out outputs/extracted-horizontal
```

The `.err` and `.end` files must be adjacent to the SQL file. Extraction verifies
completion, zero severe errors, the model-specific conditioned-zone naming
convention, unit multipliers and exactly twelve monthly heating/cooling values
per conditioned zone. Output is read-only with respect to the engine archive.

The extraction module targets these supplied IDFs; it is not a universal parser
for unrelated EnergyPlus projects. See [validation](VALIDATION.md) for the
remaining engine-warning limitation.
