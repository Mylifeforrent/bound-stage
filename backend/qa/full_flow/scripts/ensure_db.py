#!/usr/bin/env python3
"""Create the isolated QA databases if they do not exist.

Two databases are kept apart on purpose:

* ``huntai_qa``       — the running QA stack (manual walkthrough + live E2E);
* ``huntai_test_qa``  — the repository's pytest suite, which TRUNCATEs tables.

Usage (from the repository root):
    backend/.venv/bin/python backend/qa/full_flow/scripts/ensure_db.py

Never prints the DSN or password.  Requires the backend venv (asyncpg).
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg
from _qa_env import (
    admin_dsn,
    asyncpg_dsn,
    database_name,
    load_qa_env,
    replace_database,
)


async def _ensure_one(url: str) -> bool:
    db_name = database_name(url)
    try:
        conn = await asyncpg.connect(admin_dsn(url))
    except Exception as exc:  # noqa: BLE001 - message is intentionally generic
        print(f"[fail] cannot connect to PostgreSQL server ({type(exc).__name__})")
        print("       check DATABASE_URL host/port/user in .env.qa and that PostgreSQL is running")
        return False

    created = False
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if exists:
            print(f"[skip] database {db_name} already exists")
        else:
            # The identifier comes from our own env file; quote it defensively.
            quoted = '"' + db_name.replace('"', '""') + '"'
            await conn.execute(f"CREATE DATABASE {quoted}")
            print(f"[ok] created database {db_name}")
            created = True
    except asyncpg.InsufficientPrivilegeError:
        print(f"[fail] current PostgreSQL user cannot create database {db_name}")
        print(f"       create it manually, then rerun: createdb {db_name}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[fail] database setup failed ({type(exc).__name__})")
        return False
    finally:
        await conn.close()

    try:
        check = await asyncpg.connect(asyncpg_dsn(url))
    except Exception as exc:  # noqa: BLE001
        print(f"[fail] database {db_name} not reachable ({type(exc).__name__})")
        return False
    await check.close()
    if created:
        print(f"[ok] database {db_name} is reachable")
    return True


async def _ensure() -> int:
    env = load_qa_env()
    url = env["DATABASE_URL"]
    test_name = env.get("QA_TEST_DB_NAME") or "huntai_test_qa"
    test_url = replace_database(url, test_name)
    ok = await _ensure_one(url)
    ok = await _ensure_one(test_url) and ok
    return 0 if ok else 1


def main() -> int:
    return asyncio.run(_ensure())


if __name__ == "__main__":
    sys.exit(main())
