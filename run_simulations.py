"""Run archived IDFs with a supplied EnergyPlus 26.1 executable and Taiyuan EPW."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import subprocess
import time

from src.results import METRICS, annual_metrics, extract_sql, read_csv, sha256, write_csv

ROOT = Path(__file__).resolve().parent


def run_case(case, engine, weather, out):
    folder = out/case['result_id']
    folder.mkdir()
    command = [str(engine), '--weather', str(weather), '--output-directory', str(folder),
               '--idd', str(engine.parent/'Energy+.idd'), str(ROOT/case['model_path'])]
    start = time.perf_counter()
    with (folder/'stdout.log').open('w',encoding='utf-8') as log:
        result = subprocess.run(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT,check=False)
    if result.returncode:
        raise RuntimeError(f"{case['result_id']}: engine exited {result.returncode}; see {folder}")
    area, monthly = extract_sql(folder/'eplusout.sql')
    if not math.isclose(area,float(case['conditioned_m2']),rel_tol=0,abs_tol=1e-6):
        raise ValueError(f"{case['result_id']}: conditioned area changed")
    write_csv(folder/'monthly_zone_loads.csv',monthly)
    metrics = annual_metrics(monthly,area)
    return {'result_id':case['result_id'],'exit_code':result.returncode,
            'elapsed_seconds':time.perf_counter()-start, 'conditioned_m2':area,
            'idf_sha256':sha256(ROOT/case['model_path']),
            'sql_sha256':sha256(folder/'eplusout.sql'), **metrics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--energyplus',type=Path,required=True,help='Path to energyplus executable')
    parser.add_argument('--weather',type=Path,required=True,help='Path to Taiyuan CSWD EPW')
    parser.add_argument('--group',choices=['baseline','geometry','ofat','factorial','all'],default='baseline')
    parser.add_argument('--jobs',type=int,default=1)
    parser.add_argument('--out',type=Path,default=ROOT/'outputs/simulations')
    args = parser.parse_args()
    engine, weather, out = args.energyplus.resolve(), args.weather.resolve(), args.out.resolve()
    if not engine.is_file() or not weather.is_file() or not (engine.parent/'Energy+.idd').is_file():
        parser.error('Executable, adjacent Energy+.idd, and weather file must exist')
    if args.jobs < 1 or out.exists():
        parser.error('Use a positive --jobs value and a new output directory')
    source = json.loads((ROOT/'data/source_manifest.json').read_text(encoding='utf-8'))
    version = subprocess.run([str(engine),'--version'],capture_output=True,text=True,check=True).stdout.strip()
    if source['engine'] not in version:
        parser.error(f"Expected EnergyPlus {source['engine']}; found {version}")
    if sha256(weather) != source['weather']['sha256']:
        parser.error('Weather hash differs from the common archived Taiyuan EPW')
    cases = [r for r in read_csv(ROOT/'data/cases.csv') if args.group=='all' or r['group']==args.group]
    for case in cases:
        if sha256(ROOT/case['model_path']) != case['idf_sha256']:
            parser.error(f"Model checksum failed: {case['model_path']}")
    reference = {r['result_id']:r for r in read_csv(ROOT/'data/annual_results.csv')}
    out.mkdir(parents=True)
    ledger = {'engine_version':version,'weather_sha256':sha256(weather),
              'runs':[], 'failures':[], 'note':'Rerun agreement does not bound solver error.'}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_case,case,engine,weather,out):case for case in cases}
        for future in as_completed(futures):
            case = futures[future]
            try:
                record = future.result()
                record['max_reference_difference_kWh_per_m2_a'] = max(
                    abs(record[m]-float(reference[case['result_id']][m])) for m in METRICS)
                ledger['runs'].append(record)
                print(f"Completed {case['result_id']}",flush=True)
            except Exception as error:
                ledger['failures'].append({'result_id':case['result_id'],'error':str(error)})
                print(f"Failed {case['result_id']}: {error}",flush=True)
            ledger['runs'].sort(key=lambda r:r['result_id'])
            (out/'run_summary.json').write_text(json.dumps(ledger,indent=2)+'\n',encoding='utf-8')
    if ledger['failures']:
        raise SystemExit(f"{len(ledger['failures'])} failed cases; inspect {out/'run_summary.json'}")
    print(f"Completed {len(ledger['runs'])} cases; see {out/'run_summary.json'}")


if __name__ == '__main__':
    main()
