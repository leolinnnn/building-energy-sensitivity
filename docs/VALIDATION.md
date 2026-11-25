# Verification record and limitations

[← README](../README.md)

Repository preparation checked the following on **25 November 2026**:

| Check | Outcome |
| --- | --- |
| Original model/database identity | SHA-256 matched for all 170 IDFs and 170 SQL files |
| Completion | All 170 `.err` and `.end` records reported successful completion, with zero severe errors |
| Numerical extraction | 8,148 zone-month rows; all 170 annual metric records matched the source table |
| Geometry generator | All four rebuilt baseline models matched the archived EnergyPlus objects, excluding comments/formatting |
| Fresh engine execution | Four baseline IDFs rerun with EnergyPlus 26.1.0; all annual heating, cooling and combined metrics matched the archive |
| Numerical tests | Unit conversion, near-tie handling, analytical factorial contrasts and complete dataset regression checks passed |

Machine-readable records: [source audit](../data/source_verification.json) and
[baseline rerun](../data/baseline_rerun_verification.json).
The 166 nonbaseline records were re-extracted and checked against their original
databases; they were not rerun during this repository preparation.

## Known warning

The archived runs contain psychrometric temperature warnings in `PsyTwbFnTdbWPb` /
`PsyPsatFnTemp`. The baseline error logs are preserved in [data/logs](../data/logs).
The source records contain 166 runs with three warnings and four with two warnings.
Zero severe errors does not mean warning-free or fully validated.

Previous diagnostic work did not establish an annual same-input solver-error
bound. Exact agreement with a repeated run demonstrates reproducibility under
the tested installation; it does not quantify the effect of the warning or
validate a real building. Small ranking gaps should be interpreted accordingly.

## Input and output boundaries

- Geometry and room categories are conditional interpretations of drawings.
  They are not verified as-built zoning or calibrated operating models.
- Shared virtual schedules, gains and temperatures do not represent measured
  station operation. IdealLoads results are thermal loads, not purchased energy.
- Conditioned areas differ between scenarios and geometry branches. Per-area
  normalization does not establish equal function or a controlled form-only effect.
- Tested conditions cover selected discrete inputs, not the full joint parameter
  space. Scenario counts are not empirical sample sizes.

The original parameter snapshot specified `FullInteriorAndExterior`. Failed
nonconvex-zone trials led to a common `FullExterior` override in the archived
successful models. The repository parameter file records the effective setting.
No equivalence between the two solar-distribution methods is claimed.

The source SQL `Simulations` table retains `FALSE/FALSE` completion strings even
for the successfully completed runs. The extractor therefore checks both final
`.err` and `.end` records, rejects severe/fatal errors and checks complete monthly
series rather than treating those strings as Python booleans.
