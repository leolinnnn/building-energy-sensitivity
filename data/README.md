# Data and model index

[← README](../README.md)

| File | Content |
| --- | --- |
| [cases.csv](cases.csv) | 170 run identifiers, groups, scenario inputs, conditioned areas, model paths and hashes |
| [monthly_zone_loads.csv](monthly_zone_loads.csv) | 8,148 records, one per run × conditioned zone × month |
| [annual_results.csv](annual_results.csv) | Full-precision reference sums and annual per-area metrics |
| [model_parameters.json](model_parameters.json) | Common geometry, materials, glazing, operation and foundation assumptions |
| [geometry](geometry) | Floor polygons, floor-area reference and actual gridded footprints for plotting |
| [source_manifest.json](source_manifest.json) | Source-file identities, weather checksum and software version |
| [logs](logs) | Original baseline `.err` files, including warnings |

`result_id` joins the three CSV tables. Groups are `baseline` (4), `geometry` (6),
`ofat` (64) and `factorial` (96). `source_batch` retains the original research
archive labels; it is not an experiment-subject identifier.

`conditioned_m2` is the sum of the actual SQL conditioned-zone floor areas.
`changed_levels_json` records inputs changed from the common baseline.
`model_path` is relative to the repository root; `idf_sha256` verifies its bytes.
`source_sql_sha256` identifies the original database, which is retained locally
and is not distributed here. It is not the expected byte hash of a new run.

Monthly `heating_J` and `cooling_J` values are the EnergyPlus supply-air **total**
IdealLoads energies (sensible plus latent). `zone` identifies a conditioned model
zone and `month` ranges from 1 to 12. There are no participant records.

Annual `annual_heating_J` and `annual_cooling_J` sum the monthly values.
`heating_kWh_per_m2_a`, `cooling_kWh_per_m2_a` and
`ideal_total_kWh_per_m2_a` are annual ideal thermal-demand intensities.
Conversion: joules / 3,600,000 / conditioned m². No rounding is applied before
the calculations or pairwise comparisons.

Warning fields preserve the original run metadata. They do not represent an
estimated numerical uncertainty; see [validation](../docs/VALIDATION.md).

All 170 executed IDFs are in [models](../models), organized by experiment group.
