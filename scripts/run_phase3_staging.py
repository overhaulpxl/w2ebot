"""Launcher Phase 3 staging; hanya membaca .env.staging dan tidak fallback ke .env."""

import os
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
STAGING_ENV = ROOT / ".env.staging"
PLACEHOLDER_TOKEN = "REPLACE_WITH_DEDICATED_STAGING_BOT_TOKEN"
PLACEHOLDER_GUILD = "REPLACE_WITH_DEDICATED_STAGING_GUILD_ID"


def _read_staging_env(path=STAGING_ENV):
    if not path.exists():
        raise RuntimeError(".env.staging belum dibuat. Jalankan setup_phase3_staging.py.")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if "=" not in text:
            raise RuntimeError("Format .env.staging tidak valid.")
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip()
    required = (
        "STAGING_MODE", "STAGING_GUILD_ID", "DATABASE_PATH",
        "ECONOMY_V1_ENABLED", "ECONOMY_PHASE2_ENABLED", "ECONOMY_PHASE3_ENABLED",
        "DISCORD_TOKEN",
    )
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError(".env.staging belum lengkap: " + ", ".join(missing))
    if values["STAGING_MODE"].lower() != "true":
        raise RuntimeError("STAGING_MODE harus true.")
    if values["STAGING_GUILD_ID"] == PLACEHOLDER_GUILD or not values["STAGING_GUILD_ID"].isdigit():
        raise RuntimeError("STAGING_GUILD_ID harus diisi dengan snowflake staging yang valid.")
    if int(values["STAGING_GUILD_ID"]) <= 0:
        raise RuntimeError("STAGING_GUILD_ID harus positif.")
    if values["DISCORD_TOKEN"] == PLACEHOLDER_TOKEN:
        raise RuntimeError("DISCORD_TOKEN staging masih placeholder.")
    if values["DATABASE_PATH"].strip() == "":
        raise RuntimeError("DATABASE_PATH staging kosong.")
    if any(values[key].lower() != "true" for key in (
        "ECONOMY_V1_ENABLED", "ECONOMY_PHASE2_ENABLED", "ECONOMY_PHASE3_ENABLED",
    )):
        raise RuntimeError("Ketiga flag economy harus true untuk launcher staging.")
    return values


def main():
    values = _read_staging_env()
    # Set only values read from .env.staging. runtime_config skips .env in this mode.
    os.environ["W2E_STAGING_LAUNCHER"] = "1"
    os.environ.update(values)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from runtime_config import validate_startup_configuration
    config = validate_startup_configuration()
    if not config.staging_mode or config.uses_production_database:
        raise RuntimeError("Launcher menolak konfigurasi database non-staging.")
    runpy.run_path(str(ROOT / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
