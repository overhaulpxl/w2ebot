"""Jalankan simulasi deterministik market Crypto Phase 6."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.crypto_simulation import run_phase6_market_simulation


def main(argv=None):
    parser = argparse.ArgumentParser(description="Simulasi market Crypto Phase 6")
    parser.add_argument("--output", default=str(ROOT / "reports" / "economy" / "phase6-market.json"))
    args = parser.parse_args(argv)
    report = run_phase6_market_simulation()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
