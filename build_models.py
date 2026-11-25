"""Generate four baseline models from floor polygons and common parameters."""
import argparse
import json
import re
from pathlib import Path
from src.energy_model import Model, load_zones, expected_areas, GEO, PRECISION_GRID_M
from src.results import sha256

ROOT = Path(__file__).resolve().parent


def objects(text):
    """Ignore comments and formatting for comparisons against archived IDFs."""
    return re.sub(r'\s+', '', re.sub(r'!.*', '', text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'outputs/models')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Choose a new output directory; existing models are never overwritten')
    params_path = ROOT/'configs/model_parameters.json'
    params = json.loads(params_path.read_text(encoding='utf-8'))
    hashes = {'CONDITIONAL_GEOMETRY':sha256(GEO),'COMMON_PARAMETERS':sha256(params_path),
              'COMMON_WEATHER':params['weather_sha256']}
    zones, deltas = load_zones()
    expected = expected_areas()
    built, audits = {}, {}
    for prototype, geometry in zones.items():
        model = Model(prototype,geometry,params)
        model.build_horizontal()
        model.build_walls()
        model.validate(expected)
        built[prototype] = model.idf(hashes)
        archived = (ROOT/f'models/baseline/{prototype}.idf').read_text(encoding='utf-8')
        same = objects(archived)==objects(built[prototype])
        if not same:
            raise ValueError(f'Generated objects differ from archived baseline: {prototype}')
        audits[prototype] = {**model.audit(),'precision_grid_m':PRECISION_GRID_M,
                             'geometry_area_adjustment_m2':deltas[prototype],
                             'archived_objects_match':same}
    args.out.mkdir(parents=True)
    for name, text in built.items():
        (args.out/f'{name}.idf').write_text(text,encoding='utf-8',newline='\n')
    (args.out/'geometry_checks.json').write_text(json.dumps(audits,indent=2)+'\n',encoding='utf-8')
    print('Built four models; all generated IDF objects match the archived baseline models.')
    print(f'Outputs: {args.out}')


if __name__ == '__main__':
    main()
