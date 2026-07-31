"""Launcher fail-closed bot staging Phase 8."""

import os
from pathlib import Path
import runpy


def main():
    root = Path(__file__).resolve().parents[1]
    if os.getenv("STAGING_MODE", "").lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("STAGING_MODE wajib aktif.")
    for name in ("ECONOMY_V1_ENABLED", "ECONOMY_PHASE2_ENABLED", "ECONOMY_PHASE5_ENABLED",
                 "ECONOMY_PHASE6_ENABLED", "ECONOMY_PHASE8_ENABLED"):
        if os.getenv(name, "").lower() not in {"1", "true", "yes", "on"}:
            raise RuntimeError(f"{name} wajib aktif hanya pada staging.")
    database = Path(os.environ["DATABASE_PATH"]).resolve()
    if database == (root / "w2ebot.db").resolve():
        raise RuntimeError("Database production ditolak.")
    os.environ["W2E_STAGING_LAUNCHER"] = "1"
    runpy.run_path(str(root / "main.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
