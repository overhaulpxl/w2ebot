"""Konfigurasi runtime terpusat dan guard staging yang fail-closed."""

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
if os.getenv("W2E_STAGING_LAUNCHER") != "1":
    load_dotenv(PROJECT_ROOT / ".env")


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_database_path(value=None, *, project_root=PROJECT_ROOT):
    raw = str(value if value is not None else os.getenv("DATABASE_PATH", "w2ebot.db")).strip()
    if not raw:
        raw = "w2ebot.db"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(project_root) / path
    return path.resolve()


def _parse_guild_id(value):
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    parsed = int(text)
    return parsed if parsed > 0 else None


PRODUCTION_DATABASE_PATH = (PROJECT_ROOT / "w2ebot.db").resolve()
DATABASE_PATH = resolve_database_path()
DATABASE_PATH_STRING = str(DATABASE_PATH)
STAGING_MODE = _env_bool("STAGING_MODE", False)
STAGING_GUILD_ID = _parse_guild_id(os.getenv("STAGING_GUILD_ID"))
ECONOMY_V1_ENABLED = _env_bool("ECONOMY_V1_ENABLED", False)
ECONOMY_PHASE2_ENABLED = _env_bool("ECONOMY_PHASE2_ENABLED", False)
ECONOMY_PHASE3_ENABLED = _env_bool("ECONOMY_PHASE3_ENABLED", False)
ECONOMY_PHASE4_ENABLED = _env_bool("ECONOMY_PHASE4_ENABLED", False)
ECONOMY_PHASE5_ENABLED = _env_bool("ECONOMY_PHASE5_ENABLED", False)


@dataclass(frozen=True)
class StartupConfiguration:
    database_path: Path
    production_database_path: Path
    staging_mode: bool
    staging_guild_id: int | None
    discord_token_configured: bool
    economy_v1_enabled: bool
    economy_phase2_enabled: bool
    economy_phase3_enabled: bool
    economy_phase4_enabled: bool = False
    economy_phase5_enabled: bool = False

    @property
    def all_economy_flags_enabled(self):
        return self.economy_v1_enabled and self.economy_phase2_enabled and self.economy_phase3_enabled

    @property
    def marketplace_flags_enabled(self):
        return self.all_economy_flags_enabled and self.economy_phase4_enabled

    @property
    def casino_flags_enabled(self):
        return self.economy_v1_enabled and self.economy_phase2_enabled and self.economy_phase5_enabled

    @property
    def uses_production_database(self):
        return self.database_path == self.production_database_path


def current_startup_configuration():
    return StartupConfiguration(
        database_path=DATABASE_PATH,
        production_database_path=PRODUCTION_DATABASE_PATH,
        staging_mode=STAGING_MODE,
        staging_guild_id=STAGING_GUILD_ID,
        discord_token_configured=bool(os.getenv("DISCORD_TOKEN", "").strip()),
        economy_v1_enabled=ECONOMY_V1_ENABLED,
        economy_phase2_enabled=ECONOMY_PHASE2_ENABLED,
        economy_phase3_enabled=ECONOMY_PHASE3_ENABLED,
        economy_phase4_enabled=ECONOMY_PHASE4_ENABLED,
        economy_phase5_enabled=ECONOMY_PHASE5_ENABLED,
    )


def validate_startup_configuration(config=None, *, verify_database=True):
    config = config or current_startup_configuration()
    if config.staging_mode and config.uses_production_database:
        raise RuntimeError("STAGING_MODE menolak DATABASE_PATH production.")
    if config.all_economy_flags_enabled:
        if not config.staging_mode:
            raise RuntimeError("Tiga flag economy hanya dapat diaktifkan dalam STAGING_MODE.")
        if config.uses_production_database:
            raise RuntimeError("Tiga flag economy menolak database production.")
        if config.staging_guild_id is None:
            raise RuntimeError("STAGING_GUILD_ID wajib berupa Discord guild ID yang valid.")
        if not config.discord_token_configured:
            raise RuntimeError("DISCORD_TOKEN staging belum dikonfigurasi.")
        if verify_database:
            path = config.database_path
            if not path.exists() or not path.is_file():
                raise RuntimeError("DATABASE_PATH staging harus menunjuk file SQLite yang sudah ada.")
            try:
                connection = sqlite3.connect(f"file:{path.as_posix()}?mode=rw", uri=True)
                try:
                    connection.execute("PRAGMA schema_version").fetchone()
                finally:
                    connection.close()
            except sqlite3.Error as exc:
                raise RuntimeError("DATABASE_PATH staging tidak dapat dibuka dengan aman.") from exc
    if config.economy_phase4_enabled and not config.all_economy_flags_enabled:
        raise RuntimeError("ECONOMY_PHASE4_ENABLED memerlukan flag Economy Phase 1-3.")
    if config.economy_phase5_enabled and not (config.economy_v1_enabled and config.economy_phase2_enabled):
        raise RuntimeError("ECONOMY_PHASE5_ENABLED memerlukan Economy V1 dan Phase 2.")
    if config.casino_flags_enabled:
        if not config.staging_mode or config.uses_production_database:
            raise RuntimeError("Economy Phase 5 hanya dapat diaktifkan pada database staging.")
        if config.staging_guild_id is None or not config.discord_token_configured:
            raise RuntimeError("Phase 5 staging memerlukan guild dan Discord token khusus staging.")
    return config


def command_sync_guild_id(production_guild_id, config=None):
    config = config or STARTUP_CONFIGURATION
    if config.staging_mode:
        if config.staging_guild_id is None:
            raise RuntimeError("STAGING_GUILD_ID wajib untuk guild-scoped sync.")
        return config.staging_guild_id
    return int(production_guild_id)


STARTUP_CONFIGURATION = validate_startup_configuration()
