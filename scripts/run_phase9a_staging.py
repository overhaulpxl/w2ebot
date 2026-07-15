"""Fail-closed launcher for local Phase 9A staging only."""

import os
from pathlib import Path
import runpy

from dotenv import load_dotenv


def main():
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env.staging"
    if not env_path.is_file():
        raise RuntimeError(".env.staging wajib tersedia secara lokal.")
    load_dotenv(env_path, override=True)
    if os.getenv("STAGING_MODE", "").lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("STAGING_MODE wajib aktif.")
    database = Path(os.environ["DATABASE_PATH"]).expanduser().resolve()
    if database == (root / "w2ebot.db").resolve():
        raise RuntimeError("Database production ditolak.")
    if not database.is_file():
        raise RuntimeError("Database staging tidak ditemukan.")
    if not os.getenv("DASHBOARD_PUBLIC_URL", "").startswith("https://"):
        raise RuntimeError("DASHBOARD_PUBLIC_URL staging wajib HTTPS.")
    for name in (
        "DASHBOARD_DISCORD_CLIENT_ID", "DASHBOARD_DISCORD_CLIENT_SECRET", "DASHBOARD_INTERNAL_KEY_ID",
        "DASHBOARD_INTERNAL_SIGNING_KEY", "DASHBOARD_SESSION_KEY_ID", "DASHBOARD_SESSION_HASH_KEY",
        "DASHBOARD_IP_HASH_KEY",
    ):
        value = os.getenv(name, "")
        if not value or value.startswith("<") or "YOUR_" in value:
            raise RuntimeError(f"{name} staging belum valid.")
    os.environ["W2E_STAGING_LAUNCHER"] = "1"
    runpy.run_path(str(root / "main.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
