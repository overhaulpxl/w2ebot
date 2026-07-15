"""Fail-closed launcher for a locally prepared Phase 9B staging bot."""

from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _load(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main():
    env_file = ROOT / ".env.staging"
    if not env_file.exists():
        raise SystemExit(".env.staging tidak ditemukan.")
    env = os.environ.copy()
    env.update(_load(env_file))
    database = Path(env.get("DATABASE_PATH", "")).resolve()
    production = Path(env.get("PRODUCTION_DATABASE_PATH", ROOT / "w2ebot.db")).resolve()
    if database == production or not database.exists():
        raise SystemExit("Database staging tidak valid.")
    return subprocess.call([sys.executable, str(ROOT / "main.py")], cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
