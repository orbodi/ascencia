"""Entrypoint Docker : attend Postgres, migrate, seed, puis démarre uvicorn."""

from __future__ import annotations

import os
import subprocess
import sys
import time


def wait_for_db(timeout_s: int = 60) -> None:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://geminia:geminia@db:5432/geminia",
    )
    # asyncpg DSN → psycopg-style for a quick TCP/SQL check via SQLAlchemy sync
    sync_url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(sync_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            print("Postgres prêt.", flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"Attente Postgres… ({exc})", flush=True)
            time.sleep(2)
    raise RuntimeError(f"Postgres indisponible après {timeout_s}s: {last_err}")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> None:
    wait_for_db()
    run([sys.executable, "-m", "alembic", "upgrade", "head"])
    # Seed idempotent (admin + config + démo si vide)
    run([sys.executable, "-m", "scripts.seed"])

    host = os.environ.get("UVICORN_HOST", "0.0.0.0")
    port = os.environ.get("UVICORN_PORT", "8000")
    reload_flag = os.environ.get("UVICORN_RELOAD", "0") == "1"
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        port,
    ]
    if reload_flag:
        cmd.append("--reload")
    print("+", " ".join(cmd), flush=True)
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
