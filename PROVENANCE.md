# Source history and code provenance

This repository packages the four-scenario EnergyPlus study in the supplied
`THU_energy station/iccesb_2026` research archive. The results correspond to the
September 2026 research-text draft. This is ongoing research; the directory name
does not establish conference acceptance or publication.

## Source stages

The earlier sustainable-design course material used five prototypes and a
combined energy/perception decision framework. The newer study uses four
drawing-derived conditional geometry scenarios, explicit common assumptions and
traceable EnergyPlus outputs. The two stages are not pooled.

The earlier `PADcalculator.py` could substitute demonstration energy values when
input labels did not match. Its composite rankings, questionnaire inputs and
unverified historical energy figures are not used in this repository's results.

## Files retained and adapted

| Repository content | Origin and treatment |
| --- | --- |
| `models/` | Byte-for-byte copies of the 170 executed IDFs listed in the research results index |
| `data/geometry/` | Original conditional floor polygons, area reference and gridded plotting geometry |
| `src/energy_model.py` | Geometry and EnergyPlus object-generation core from `build_exploratory_idfs.py`; local path setup and archive-specific CLI/gates replaced |
| `data/model_parameters.json` | Original common parameter values; effective `FullExterior` setting recorded, local paths and obsolete workflow flags removed |
| `data/monthly_zone_loads.csv` | Newly extracted from the 170 source SQL databases, with original numerical precision |
| `data/annual_results.csv` | Recomputed from those monthly values and checked against the source results index |
| Portable CLI, analysis and plotting | Repository preparation code, implementing the documented source calculations and comparison rules |

Original model/SQL hashes are stored in `data/cases.csv`. Original generator,
parameter and results-index hashes are in `data/source_manifest.json`. The source
generator's geometry and object-generation algorithms are retained. Changes to
input paths and header comments mean regenerated model files are compared by
their EnergyPlus objects, not by whole-file byte identity.

The portable extraction, analysis, tests, English documentation and figures were
prepared with coding-assistant support. Their creation during repository
preparation is distinct from the archived simulation study.

## Excluded material

Full manuscripts, application documents, course-group presentation files, raw CAD
working files, engine binaries, weather binaries, personal paths and the roughly
3.2 GB source SQL archive are not included. The source drawings remain the
upstream record; this release supplies the geometry needed for model generation.

## Software and preparation references

- [EnergyPlus 26.1 input/output reference](https://bigladdersoftware.com/epx/docs/26-1/input-output-reference/group-zone-forced-air-units.html): IdealLoads output definitions.
- [Shapely](https://shapely.readthedocs.io/): polygon topology and precision handling.
- [Matplotlib](https://matplotlib.org/): regenerated research figures.
- Kassis, T., Agarwal, V., He, Y., Patel, D. & Brueckner, A. M. (2026).
  [Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
  The Matplotlib skill informed the plotting workflow used during repository preparation.
