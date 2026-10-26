#!/usr/bin/env python3
"""Create the isolated QA environment file.

Usage (from the repository root):
    backend/.venv/bin/python backend/qa/full_flow/scripts/init_env.py [--force]

The generated `.env.qa` is gitignored and is never printed.  A fresh run
generates local-only random secrets; `--force` rotates them.
"""

from __future__ import annotations

import argparse
import sys

from _qa_env import (
    ENV_FILE,
    REPO_ROOT,
    REQUIRED_KEYS,
    default_values,
    parse_env,
    require_keys,
    write_env,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="regenerate secrets and overwrite")
    args = parser.parse_args()

    if ENV_FILE.exists() and not args.force:
        current = parse_env(ENV_FILE)
        missing = require_keys(current, REQUIRED_KEYS)
        print(f"[skip] {ENV_FILE} already exists ({len(current)} keys)")
        if missing:
            print(f"[warn] missing keys: {', '.join(missing)}; rerun with --force")
            return 1
        print("       keep it, or rerun with --force to rotate local secrets")
        return 0

    root_env = parse_env(REPO_ROOT / ".env")
    values = default_values(root_env)
    write_env(ENV_FILE, values)

    print(f"[ok] wrote {ENV_FILE}")
    print(f"     keys: {len(values)} (local secrets generated, values not shown)")
    print("     root .env was read for DATABASE_URL only; it was not modified")
    missing = require_keys(values, REQUIRED_KEYS)
    if missing:
        print(f"[fail] still missing: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
