#!/usr/bin/env python3
"""security_advisors_check.py — Supabase get_advisors gate (card E2.1).

Ultraplan P1 DoD: "supabase get_advisors = 0 ERROR". That call is a Supabase
Management API read against a HOSTED project — it cannot run before the app
Postgres is provisioned. This script is the gate: it runs the exact
`advisors/security` + `advisors/performance` calls whenever credentials exist
and exits non-zero on any ERROR-level finding.

Credentials (never committed; env only):
  SUPABASE_ACCESS_TOKEN        management API token (supabase login)
  GAMMASUMMIT_SUPABASE_PROJECT_REF   hosted project ref

Without credentials: exits 0 with SKIP status unless --require-credentials,
so CI stays honest (the log says SKIPPED, never "clean"). The local security
posture is meanwhile enforced by db/tests/0002_grants_regression.sql.

Usage:
  python3 scripts/security_advisors_check.py
  python3 scripts/security_advisors_check.py --require-credentials

Exit codes: 0 clean/skip, 1 ERROR-level findings, 2 usage/IO error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.supabase.com/v1/projects/{ref}/advisors/{kind}"


def fetch_advisors(token: str, ref: str, kind: str) -> dict:
    req = urllib.request.Request(
        API.format(ref=ref, kind=kind),
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Supabase get_advisors ERROR gate")
    ap.add_argument(
        "--require-credentials",
        action="store_true",
        help="fail instead of skipping when credentials are missing",
    )
    args = ap.parse_args(argv)

    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    ref = os.environ.get("GAMMASUMMIT_SUPABASE_PROJECT_REF", "")
    if not token or not ref:
        msg = (
            "SKIP security-advisors: SUPABASE_ACCESS_TOKEN / "
            "GAMMASUMMIT_SUPABASE_PROJECT_REF not set (app Postgres not provisioned)"
        )
        print(msg)
        return 2 if args.require_credentials else 0

    total_errors = 0
    for kind in ("security", "performance"):
        try:
            payload = fetch_advisors(token, ref, kind)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"ERROR security-advisors {kind}: {exc}", file=sys.stderr)
            return 2
        findings = payload if isinstance(payload, list) else payload.get("data", [])
        errors = [
            f
            for f in findings
            if str(f.get("level", f.get("severity", ""))).lower() == "error"
        ]
        total_errors += len(errors)
        print(f"{kind}: {len(findings)} finding(s), {len(errors)} ERROR")
        for finding in errors:
            print(json.dumps(finding))

    if total_errors:
        print(f"security-advisors: {total_errors} ERROR-level finding(s)")
        return 1
    print("security-advisors: 0 ERROR")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
