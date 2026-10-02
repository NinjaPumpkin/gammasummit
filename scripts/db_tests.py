#!/usr/bin/env python3
"""db_tests.py — apply migrations + run pgtap suites against a database.

One entry point for CI and local verification (card E2.1):
  1. apply db/migrations/NNNN_*.sql in order to the target DB (ON_ERROR_STOP)
  2. run every db/tests/*.sql file as psql (pgtap TAP output)
  3. parse TAP: plan count must match, zero "not ok" lines

Any failure exits non-zero. Nothing here writes outside the target DB and no
credentials live in this file — the connection arrives via --psql-cmd or
--db-url (env/GAMMASUMMIT_* injection happens above this script).

Usage:
  python3 scripts/db_tests.py --psql-cmd "docker exec -i gs-pg psql -X -U postgres"
  python3 scripts/db_tests.py --db-url postgresql://user:pass@host/db   (psql on PATH)
  python3 scripts/db_tests.py --apply-only ...       # migrations only
  python3 scripts/db_tests.py --tests-only ...       # pgtap only

Exit codes: 0 clean, 1 failure, 2 usage/IO error.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import shlex
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS = os.path.join(REPO, "db", "migrations")
TESTS = os.path.join(REPO, "db", "tests")

OK_RE = re.compile(r"^ok \d+")
NOT_OK_RE = re.compile(r"^not ok \d+")
PLAN_RE = re.compile(r"^(\d+)\.\.(\d+)")


def run_sql(base_cmd: list[str], sql: str, label: str) -> subprocess.CompletedProcess:
    """Feed SQL to the psql command; ON_ERROR_STOP is the caller's business."""
    proc = subprocess.run(
        base_cmd, input=sql, capture_output=True, text=True
    )
    if proc.returncode != 0:
        print(f"FAIL {label}: psql exit {proc.returncode}")
        if proc.stdout:
            print(proc.stdout[-4000:])
        if proc.stderr:
            print(proc.stderr[-4000:])
    return proc


def parse_tap(output: str) -> tuple[int, int, int | None]:
    """Return (ok_count, not_ok_count, declared_plan). Non-TAP lines ignored."""
    ok = not_ok = 0
    plan: int | None = None
    for line in output.splitlines():
        line = line.strip()
        if NOT_OK_RE.match(line):
            not_ok += 1
        elif OK_RE.match(line):
            ok += 1
        else:
            m = PLAN_RE.match(line)
            if m:
                plan = int(m.group(2))
    return ok, not_ok, plan


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Apply migrations + run pgtap suites")
    ap.add_argument("--psql-cmd", help='psql command prefix, e.g. "psql -X -q"')
    ap.add_argument("--db-url", help="connection string (builds the psql command)")
    ap.add_argument("--apply-only", action="store_true", help="only apply migrations")
    ap.add_argument("--tests-only", action="store_true", help="only run db/tests")
    args = ap.parse_args(argv)

    if args.psql_cmd:
        base_cmd = shlex.split(args.psql_cmd)
    elif args.db_url:
        base_cmd = ["psql", args.db_url]
    else:
        print("usage: db_tests.py --psql-cmd '...' | --db-url '...'", file=sys.stderr)
        return 2
    base_cmd += ["-X", "-q", "-v", "ON_ERROR_STOP=1"]

    failures = 0

    if not args.tests_only:
        names = sorted(glob.glob(os.path.join(MIGRATIONS, "*.sql")))
        if not names:
            print(f"no migrations in {MIGRATIONS}", file=sys.stderr)
            return 2
        for path in names:
            name = os.path.basename(path)
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            # Law (migration_lint doc): the runner wraps each migration in its
            # own transaction — a failed file leaves zero partial state.
            proc = run_sql(base_cmd, "BEGIN;\n" + body + "\nCOMMIT;", f"apply {name}")
            if proc.returncode != 0:
                failures += 1
                break
            print(f"ok   apply {name}")
        if failures == 0:
            print(f"migrations applied clean: {len(names)} file(s)")

    if args.apply_only:
        return 1 if failures else 0

    # pgtap is a test dependency (not schema) — provision it into the target.
    proc = run_sql(base_cmd, "CREATE EXTENSION IF NOT EXISTS pgtap;", "bootstrap pgtap")
    if proc.returncode != 0:
        return 1

    names = sorted(glob.glob(os.path.join(TESTS, "*.sql")))
    if not names:
        print(f"no test files in {TESTS}", file=sys.stderr)
        return 2
    for path in names:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            proc = run_sql(base_cmd + ["-t", "-A"], fh.read(), f"test {name}")
        if proc.returncode != 0:
            failures += 1
            continue
        ok, not_ok, plan = parse_tap(proc.stdout)
        planned = plan is not None and plan == ok + not_ok
        passed = proc.returncode == 0 and not_ok == 0 and planned and ok > 0
        status = "ok  " if passed else "FAIL"
        print(f"{status} test {name}: {ok} ok / {not_ok} not ok / plan {plan}")
        if not passed:
            failures += 1
            print(proc.stdout[-4000:])

    if failures:
        print(f"db-tests: {failures} failure(s)")
        return 1
    print(f"db-tests: {len(names)} suite(s) green")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
