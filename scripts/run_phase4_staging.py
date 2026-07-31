"""Launcher Phase 4 staging; membaca .env.staging tanpa fallback production."""

import os
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
STAGING_ENV = ROOT / ".env.staging"
PLACEHOLDER_TOKEN = "REPLACE_WITH_DEDICATED_STAGING_BOT_TOKEN"
PLACEHOLDER_GUILD = "REPLACE_WITH_DEDICATED_STAGING_GUILD_ID"


def read_staging_env(path=STAGING_ENV):
    if not path.exists():
        raise RuntimeError(".env.staging belum dibuat.")
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
        "STAGING_MODE", "STAGING_GUILD_ID", "DATABASE_PATH", "DISCORD_TOKEN",
        "ECONOMY_V1_ENABLED", "ECONOMY_PHASE2_ENABLED", "ECONOMY_PHASE3_ENABLED",
        "ECONOMY_PHASE4_ENABLED",
    )
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("Konfigurasi staging belum lengkap: " + ", ".join(missing))
    if values["STAGING_MODE"].lower() != "true":
        raise RuntimeError("STAGING_MODE wajib true.")
    if values["STAGING_GUILD_ID"] == PLACEHOLDER_GUILD or not values["STAGING_GUILD_ID"].isdigit():
        raise RuntimeError("STAGING_GUILD_ID staging tidak valid.")
    if values["DISCORD_TOKEN"] in ("", PLACEHOLDER_TOKEN):
        raise RuntimeError("DISCORD_TOKEN staging masih kosong atau placeholder.")
    if any(values[key].lower() != "true" for key in required[-4:]):
        raise RuntimeError("Keempat flag economy wajib true hanya pada staging Phase 4.")
    database = Path(values["DATABASE_PATH"]).expanduser().resolve()
    if database == (ROOT / "w2ebot.db").resolve() or not database.is_file():
        raise RuntimeError("DATABASE_PATH staging tidak valid atau menunjuk production.")
    return values


def main():
    values = read_staging_env()
    os.environ["W2E_STAGING_LAUNCHER"] = "1"
    os.environ.update(values)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from runtime_config import validate_startup_configuration
    from economy.phase4_migrations import verify_phase4_staging
    import asyncio
    config = validate_startup_configuration()
    if not config.marketplace_flags_enabled or config.uses_production_database:
        raise RuntimeError("Launcher menolak konfigurasi non-staging.")
    verification = asyncio.run(verify_phase4_staging(config.database_path))
    if not verification["schema_capable"]:
        raise RuntimeError("Database staging belum memiliki migration Phase 4 yang valid.")
    runpy.run_path(str(ROOT / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
