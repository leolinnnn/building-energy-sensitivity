# Archived reference results

[← Overview](../README.md) · [Validation](../docs/VALIDATION.md)

| File or directory | Observation or purpose | Used by |
| --- | --- | --- |
| [annual_results.csv](annual_results.csv) | One full-precision annual result per `result_id`; 170 rows | `run_analysis.py` after recomputation; `run_simulations.py` after solver runs |
| [geometry/floor_geometry_qa.csv](geometry/floor_geometry_qa.csv) | Archived area expectations for each scenario/floor | `src/energy_model.py` to validate generated geometry |
| [validation/source_verification.json](validation/source_verification.json) | Preparation audit of 170 original IDF/SQL records | Source verification record |
| [validation/baseline_rerun_verification.json](validation/baseline_rerun_verification.json) | Four executed baseline reruns | Solver-reproduction record |
| [logs/](logs/) | Original baseline EnergyPlus error/warning logs | Warning review |

These files are retained comparison targets and audit records. New output belongs
in `outputs/`; replacing a reference file requires a documented research revision.
The geometry QA table validates model construction; it is not a calibration input.
Annual field units and identifiers are documented in the [data dictionary](../data/README.md).
