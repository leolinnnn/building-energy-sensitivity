"""Extract monthly zone loads and annual metrics from one completed run."""
import argparse
import json
from pathlib import Path
from src.results import annual_metrics, extract_sql, write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sql',type=Path,required=True,help='eplusout.sql with adjacent .err and .end')
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Choose a new output directory')
    area, monthly = extract_sql(args.sql)
    write_csv(args.out/'monthly_zone_loads.csv',monthly)
    result = {'conditioned_m2':area, **annual_metrics(monthly,area)}
    (args.out/'annual_metrics.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
