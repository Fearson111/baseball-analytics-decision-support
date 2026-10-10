"""Fetch and grade only the financial portfolio's MLB results for one date."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from all_seeing_eye.financial_system.results import scan_day


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat(), help="Portfolio slate date (YYYY-MM-DD)")
    args = parser.parse_args()
    report = scan_day(ROOT, args.date)
    print(json.dumps(report, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

