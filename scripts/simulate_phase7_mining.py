"""Jalankan simulasi deterministik Mining Phase 7."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from economy.mining_simulation import run_mining_simulation


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = run_mining_simulation(seeds=20, days=90)
    payload = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8", newline="\n")
    print(json.dumps({"artifactHash": result["artifactHash"], "passed": result["passed"],
                      "summary": result["artifact"]["summary"]}, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
