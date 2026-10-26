#!/usr/bin/env python3
"""Pre-flight check for the full-flow QA kit.

Usage (from the repository root):
    backend/.venv/bin/python backend/qa/full_flow/scripts/doctor.py

Exit code 0 = ready; 1 = at least one blocking problem.
No secret values are printed.
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import sys
import urllib.request

import asyncpg
from _qa_env import (
    ENV_FILE,
    PACKAGE_DIR,
    REPO_ROOT,
    REQUIRED_KEYS,
    RUNTIME_DIR,
    asyncpg_dsn,
    database_name,
    load_qa_env,
    parse_env,
    require_keys,
)

FAIL: list[str] = []
WARN: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"[ok]   {label}{(' — ' + detail) if detail else ''}")


def warn(label: str, detail: str = "") -> None:
    WARN.append(label)
    print(f"[warn] {label}{(' — ' + detail) if detail else ''}")


def fail(label: str, detail: str = "") -> None:
    FAIL.append(label)
    print(f"[fail] {label}{(' — ' + detail) if detail else ''}")


def _version(command: str, *args: str) -> str | None:
    try:
        out = subprocess.run(
            [command, *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    if out.returncode != 0:
        return None
    text = (out.stdout or out.stderr).strip().splitlines()
    return text[0] if text else ""


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _pid_alive(name: str) -> bool:
    pidfile = RUNTIME_DIR / "pids" / f"{name}.pid"
    if not pidfile.exists():
        return False
    try:
        pid = int(pidfile.read_text().strip())
    except OSError, ValueError:
        return False
    try:
        import os

        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.status == 200
    except Exception:  # noqa: BLE001
        return False


async def _check_db(url: str) -> None:
    db_name = database_name(url)
    try:
        conn = await asyncpg.connect(asyncpg_dsn(url))
    except Exception as exc:  # noqa: BLE001
        fail(f"database {db_name}", f"cannot connect ({type(exc).__name__})")
        return
    try:
        value = await conn.fetchval("SELECT 1")
        if value == 1:
            ok(f"database {db_name}", "reachable")
    finally:
        await conn.close()


def main() -> int:
    print("HuntAI Test · full-flow QA doctor")
    print(f"repo: {REPO_ROOT}")
    print(f"kit : {PACKAGE_DIR}")
    print()

    # pyproject requires >=3.14; report the exact interpreter for the record.
    ok("Python", sys.version.split()[0])

    for command, args in (
        ("uv", ("--version",)),
        ("node", ("--version",)),
        ("npm", ("--version",)),
        ("docker", ("--version",)),
        ("curl", ("--version",)),
    ):
        if shutil.which(command) is None:
            fail(command, "not found in PATH")
            continue
        line = _version(command, *args)
        if line is None:
            fail(command, "installed but does not run")
        else:
            ok(command, line)

    if shutil.which("docker"):
        server = _version("docker", "info", "--format", "{{.ServerVersion}}")
        if server:
            ok("Docker daemon", server)
        else:
            fail("Docker daemon", "not running (needed for Jenkins)")

    print()
    if not ENV_FILE.exists():
        fail(".env.qa", "missing; run qa.sh init")
        print()
        print("Run `backend/qa/full_flow/qa.sh init` first.")
        return 1

    env = load_qa_env()
    missing = require_keys(env, REQUIRED_KEYS)
    if missing:
        fail(".env.qa", "missing keys: " + ", ".join(missing))
    else:
        ok(".env.qa", f"{len(parse_env(ENV_FILE))} keys")

    for key in ("JENKINS_WEBHOOK_SECRET", "JENKINS_API_TOKEN"):
        if not env.get(key, "").strip():
            fail(key, "empty; Jenkins webhook/trigger will not work")
        else:
            ok(key, "present (value not shown)")

    # Ports.  Our own running stack is fine; a foreign process is not.
    # Mock integrations may be shared with an existing local stack.
    port_expectations = (
        ("QA_API_PORT", "8013", "API", "api"),
        ("QA_WEB_PORT", "5180", "Vite", "web"),
        ("QA_IDP_PORT", "8190", "mock IdP", "mock-idp"),
        ("QA_JENKINS_PORT", "8088", "Jenkins", None),
        ("QA_MOCK_PORT", "8091", "mock integrations", None),
    )
    for key, default, label, pid_name in port_expectations:
        port = int(env.get(key, default))
        occupied = _port_open("127.0.0.1", port)
        if not occupied:
            ok(f"port {port} ({label})", "free")
        elif key == "QA_MOCK_PORT":
            warn(f"port {port} ({label})", "already listening; the kit will reuse it")
        elif pid_name is not None and _pid_alive(pid_name):
            ok(f"port {port} ({label})", "already running (started by this kit)")
        elif key == "QA_JENKINS_PORT" and _http_ok(
            f"http://127.0.0.1:{port}/job/full-flow-smoke/api/json"
        ):
            ok(f"port {port} ({label})", "already running")
        else:
            fail(
                f"port {port} ({label})",
                "already in use by a foreign process; stop it or change the QA_* port",
            )

    print()
    asyncio.run(_check_db(env["DATABASE_URL"]))

    print()
    if FAIL:
        print(f"RESULT: NOT READY ({len(FAIL)} blocking problem(s), {len(WARN)} warning(s))")
        return 1
    print(f"RESULT: READY ({len(WARN)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
