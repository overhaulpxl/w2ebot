"""Launcher fail-closed Crypto Phase 6; hanya membaca .env.staging."""

import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
STAGING_ENV = ROOT / ".env.staging"


def read_staging_env(path=STAGING_ENV):
    if not path.exists():
        raise RuntimeError(".env.staging belum dibuat.")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            if "=" not in text:
                raise RuntimeError("Format .env.staging tidak valid.")
            key, value = text.split("=", 1)
            values[key.strip()] = value.strip()
    required = ("STAGING_MODE", "STAGING_GUILD_ID", "DATABASE_PATH", "DISCORD_TOKEN",
                "ECONOMY_V1_ENABLED", "ECONOMY_PHASE6_ENABLED")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("Konfigurasi staging belum lengkap: " + ", ".join(missing))
    if values["STAGING_MODE"].lower() != "true" or any(
        values[key].lower() != "true" for key in ("ECONOMY_V1_ENABLED", "ECONOMY_PHASE6_ENABLED")
    ):
        raise RuntimeError("Staging Phase 6 memerlukan STAGING_MODE, V1, dan Phase 6 true.")
    if not values["STAGING_GUILD_ID"].isdigit() or values["DISCORD_TOKEN"].startswith("REPLACE_"):
        raise RuntimeError("Guild atau token staging masih placeholder.")
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
    from economy.phase6_migrations import verify_phase6_staging
    from runtime_config import validate_startup_configuration
    config = validate_startup_configuration()
    verification = verify_phase6_staging(config.database_path)
    if not config.crypto_flags_enabled or config.uses_production_database or not verification["schemaCapable"]:
        raise RuntimeError("Launcher menolak konfigurasi atau schema Crypto staging.")
    runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
