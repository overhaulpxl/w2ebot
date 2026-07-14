"""Launcher fail-closed bot staging Phase 7."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _load_staging_env(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main():
    env_path = ROOT / ".env.staging"
    if not env_path.exists():
        raise RuntimeError(".env.staging tidak tersedia.")
    values = _load_staging_env(env_path)
    required_true = ("STAGING_MODE", "ECONOMY_V1_ENABLED", "ECONOMY_PHASE2_ENABLED", "ECONOMY_PHASE7_ENABLED")
    if any(values.get(key, "").lower() != "true" for key in required_true):
        raise RuntimeError("Flag staging Phase 7 belum lengkap.")
    if not values.get("DISCORD_TOKEN") or not values.get("STAGING_GUILD_ID"):
        raise RuntimeError("Token dan guild staging wajib diisi.")
    environment = os.environ.copy()
    environment.update(values)
    environment["W2E_STAGING_LAUNCHER"] = "1"
    return subprocess.call([sys.executable, str(ROOT / "main.py")], cwd=ROOT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
