"""Run the deterministic Living PRD generator and verifier."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent


def _run(script_name: str) -> int:
    result = subprocess.run([sys.executable, str(SCRIPTS_DIR / script_name)], check=False)
    return result.returncode


def main() -> int:
    print("Generating AI handoff...")
    code = _run("generate_ai_handoff.py")
    if code:
        return code
    print("Verifying AI handoff...")
    return _run("verify_ai_handoff.py")


if __name__ == "__main__":
    raise SystemExit(main())
