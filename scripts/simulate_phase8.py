"""Jalankan simulasi acceptance Phase 8."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.phase8_simulation import run_phase8_simulation


def main():
    report = run_phase8_simulation()
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
