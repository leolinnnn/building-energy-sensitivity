"""Reproduce annual metrics and rank sensitivity from the bundled monthly data."""
from __future__ import annotations
import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from src.results import METRICS, annual_metrics, read_csv, write_csv, sha256
from src.sensitivity import compare_conditions, factorial_contrasts

ROOT = Path(__file__).resolve().parent


def reproduce(out: Path, check_models: bool = False) -> tuple[list[dict], dict]:
    cases = read_csv(ROOT/'data/cases.csv')
    if len(cases) != len({r['result_id'] for r in cases}) or len(cases) != 170:
        raise ValueError('Expected 170 unique archived run identifiers')
    monthly = defaultdict(list)
    for row in read_csv(ROOT/'data/monthly_zone_loads.csv'):
        monthly[row['result_id']].append(row)
    if set(monthly) != {r['result_id'] for r in cases}:
        raise ValueError('Case/monthly identifiers differ')
    reference = {r['result_id']:r for r in read_csv(ROOT/'data/annual_results.csv')}
    if set(reference) != set(monthly):
        raise ValueError('Case/annual identifiers differ')
    results, max_diff = [], 0.0
    for case in cases:
        rows = monthly[case['result_id']]
        keys = [(r['zone'],int(r['month'])) for r in rows]
        expected = {(zone,month) for zone,_ in keys for month in range(1,13)}
        if len(keys) != len(set(keys)) or set(keys) != expected:
            raise ValueError(f"Incomplete/duplicate monthly series: {case['result_id']}")
        area = float(case['conditioned_m2'])
        values = annual_metrics(rows, area)
        saved = reference[case['result_id']]
        for key, value in {'conditioned_m2':area, **values}.items():
            if not math.isclose(value,float(saved[key]),rel_tol=1e-12,abs_tol=1e-9):
                raise ValueError(f"Reference mismatch: {case['result_id']}/{key}")
        max_diff = max(max_diff, *(abs(values[k]-float(saved[k])) for k in METRICS))
        if check_models and sha256(ROOT/case['model_path']) != case['idf_sha256']:
            raise ValueError(f"Model hash mismatch: {case['model_path']}")
        results.append({**case, **values})
    summary, pairs = compare_conditions(results)
    summary.update({'run_count':len(cases), 'group_counts':dict(Counter(r['group'] for r in cases)),
                    'max_reference_difference_kWh_per_m2_a':max_diff,
                    'model_hashes_verified':len(cases) if check_models else 0})
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out/'annual_results.csv',results)
    write_csv(out/'pairwise_comparisons.csv',pairs)
    write_csv(out/'factorial_contrasts.csv',factorial_contrasts(results))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return results, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'outputs/analysis')
    parser.add_argument('--check-models',action='store_true')
    parser.add_argument('--figures',action='store_true',help='Requires matplotlib and numpy')
    args = parser.parse_args()
    results, summary = reproduce(args.out, args.check_models)
    if args.figures:
        from src.figures import make_figures
        make_figures(results,args.out/'figures')
    print(f"Reproduced {summary['run_count']} run records; maximum reference difference "
          f"{summary['max_reference_difference_kWh_per_m2_a']:.3g} kWh/m2/year.")
    for group in ['ofat','factorial']:
        counts = [summary[group]['metrics'][m]['conditions_with_reversal'] for m in METRICS]
        print(f"{group}: heating / cooling / combined reversal conditions = {counts}; "
              f"out of {summary[group]['condition_count']} conditions")
    print(f'Outputs: {args.out}')


if __name__ == '__main__':
    main()
