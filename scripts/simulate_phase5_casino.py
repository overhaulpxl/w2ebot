"""Jalankan simulasi penerimaan D18 Casino Phase 5."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.casino_simulation import run_d18_simulation


def main(argv=None):
    parser = argparse.ArgumentParser(description="Simulasi deterministik Casino D18")
    parser.add_argument("--output", default=str(ROOT / "reports" / "economy" / "phase5-d18.json"))
    parser.add_argument("--workers", type=int)
    args = parser.parse_args(argv)
    report = run_d18_simulation(workers=args.workers)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
