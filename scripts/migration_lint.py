#!/usr/bin/env python3
"""migration_lint.py — forward-only SQL migration lint harness.

Gate behind every PR (docs/build/code-structure-and-release.md §4/§5):
migrations are expand/contract, reviewed as SQL, and destructive data
operations never ride app releases.

Rules per file db/migrations/NNNN_snake_name.sql:
  1. filename matches ^\\d{4}_[a-z0-9_]+\\.sql$
  2. numeric prefixes are unique (ascending by name; gaps allowed)
  3. no destructive DDL: DROP TABLE/SCHEMA/DATABASE/VIEW, DROP COLUMN,
     TRUNCATE
  4. no unguarded DML: UPDATE/DELETE without WHERE
  5. deny-default grants: no GRANT ALL, no GRANT ... TO PUBLIC
  6. no explicit transaction control (BEGIN/COMMIT/ROLLBACK) — the runner
     wraps each migration in its own transaction
  7. at least one statement per file

Escape hatch: a file containing the line
  -- migration-lint: allow destructive
downgrades rules 3–4 to warnings (contract-phase migrations, post-cutover
only, export-first — docs/build/code-structure-and-release.md §4).

Usage:
  python3 scripts/migration_lint.py                 # lint db/migrations/
  python3 scripts/migration_lint.py <dir>           # lint another dir
  python3 scripts/migration_lint.py --json          # machine-readable findings

Exit codes: 0 clean (warnings allowed), 1 errors found, 2 usage/IO error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(REPO, "db", "migrations")

FILENAME_RE = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")
ALLOW_MARKER = "-- migration-lint: allow destructive"

# (rule_id, compiled regex, message) — evaluated on comment-stripped SQL.
DESTRUCTIVE_RULES = [
    ("destructive-ddl", re.compile(r"\bDROP\s+(TABLE|SCHEMA|DATABASE|VIEW)\b", re.I),
     "DROP TABLE/SCHEMA/DATABASE/VIEW is destructive — expand/contract only"),
    ("destructive-ddl", re.compile(r"\bALTER\s+TABLE\b[\s\S]*?\bDROP\s+COLUMN\b", re.I),
     "DROP COLUMN is destructive — contract phase only, post-cutover + export"),
    ("destructive-ddl", re.compile(r"\bTRUNCATE\b", re.I),
     "TRUNCATE is destructive — export-first, then a dedicated --dry-run job"),
]
GUARDED_RULES = [
    ("unguarded-dml", re.compile(r"^(UPDATE|DELETE)\b", re.I),
     "UPDATE/DELETE without WHERE — add a WHERE or use a dedicated --dry-run job"),
]
ALWAYS_RULES = [
    ("deny-default-grant", re.compile(r"\bGRANT\s+ALL\b", re.I),
     "GRANT ALL violates deny-default grants"),
    ("deny-default-grant", re.compile(r"\bTO\s+PUBLIC\b", re.I),
     "GRANT ... TO PUBLIC violates deny-default grants"),
]
TXN_RE = re.compile(r"^(BEGIN|COMMIT|ROLLBACK)\b", re.I)


def strip_comments(sql: str, mask_dollar: bool = True) -> str:
    """Blank out -- and /* */ comments and single-quoted string bodies in
    place (line numbers preserved). `mask_dollar=False` additionally keeps
    dollar-quoted (function-body) content: that content is real executable
    SQL, so destructive rules must see it — but statement splitting masks it
    so ';' inside a body cannot break statements apart."""
    out = list(sql)
    i, n = 0, len(sql)
    mode = None  # None | 'line' | 'block' | 'str' | dollar-tag
    dollar_tag = ""
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if mode is None:
            if ch == "-" and nxt == "-":
                mode = "line"
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if ch == "/" and nxt == "*":
                mode = "block"
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if ch == "'":
                mode = "str"
            elif ch == "$":
                m = re.match(r"\$[A-Za-z_]*\$", sql[i:])
                if m:
                    dollar_tag = m.group(0)
                    mode = "dollar"
                    i += len(dollar_tag)
                    continue
            i += 1
            continue
        if mode == "line":
            if ch == "\n":
                mode = None
            else:
                out[i] = " "
            i += 1
            continue
        if mode == "block":
            if ch == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                mode = None
                i += 2
                continue
            if ch != "\n":
                out[i] = " "
            i += 1
            continue
        if mode == "str":
            if ch == "'":
                if nxt == "'":  # escaped quote
                    out[i] = out[i + 1] = " "
                    i += 2
                    continue
                mode = None
            elif ch != "\n":
                out[i] = " "
            i += 1
            continue
        if mode == "dollar":
            if sql.startswith(dollar_tag, i):
                i += len(dollar_tag)
                mode = None
                continue
            if mask_dollar and ch != "\n":
                out[i] = " "
            i += 1
            continue
    return "".join(out)


def split_statements(sql: str) -> list[tuple[int, str]]:
    """Split comment/literal-masked SQL on top-level ';' → [(start_line, stmt)].
    Character-level: several statements on one line split correctly."""
    stmts: list[tuple[int, str]] = []
    cur: list[str] = []
    line = 1
    cur_start: int | None = None
    for ch in sql:
        if cur_start is None and not ch.isspace():
            cur_start = line
        if ch == "\n":
            line += 1
        cur.append(ch)
        if ch == ";":
            text = "".join(cur)
            if text.strip():
                stmts.append((cur_start or 1, text))
            cur = []
            cur_start = None
    tail = "".join(cur)
    if tail.strip():
        stmts.append((cur_start or 1, tail))
    return stmts


def lint_text(sql: str) -> list[dict]:
    """Return findings for one migration body.

    Two scan variants: destructive/grant rules see dollar-quoted function
    bodies (executable SQL must be reviewed too); statement rules use the
    fully masked variant so ';' inside a body cannot split statements.
    Line numbers come from match offsets in the comment-stripped text."""
    findings: list[dict] = []
    allow = ALLOW_MARKER in sql
    clean_scan = strip_comments(sql, mask_dollar=False)  # bodies visible
    clean = strip_comments(sql)  # bodies masked → statement view

    def _find(rule_id: str, rx: re.Pattern, msg: str, severity: str = "error") -> None:
        for m in rx.finditer(clean_scan):
            line_no = clean_scan.count("\n", 0, m.start()) + 1
            findings.append({"rule": rule_id, "line": line_no, "severity": severity, "msg": msg})

    for rule_id, rx, msg in ALWAYS_RULES:
        _find(rule_id, rx, msg)
    sev = "warning" if allow else "error"
    for rule_id, rx, msg in DESTRUCTIVE_RULES:
        _find(rule_id, rx, msg, severity=sev)

    for start_line, stmt in split_statements(clean):
        head = stmt.strip()
        if TXN_RE.match(head):
            findings.append({
                "rule": "txn-control", "line": start_line, "severity": "error",
                "msg": "explicit transaction control — the migration runner owns transactions",
            })
        for rule_id, rx, msg in GUARDED_RULES:
            if rx.match(head) and not re.search(r"\bWHERE\b", head, re.I):
                findings.append({"rule": rule_id, "line": start_line, "severity": sev, "msg": msg})

    if not split_statements(clean):
        findings.append({"rule": "empty-migration", "line": 1, "severity": "error",
                         "msg": "migration contains no statements"})
    return findings


def lint_dir(path: str) -> dict:
    """Lint every migration in `path`. Returns {files, findings, errors}."""
    all_findings: list[dict] = []
    try:
        names = sorted(f for f in os.listdir(path) if f.endswith(".sql"))
    except OSError as exc:
        return {"files": 0, "findings": [], "errors": [f"cannot read {path}: {exc}"]}
    prefixes: dict[str, str] = {}
    errors: list[str] = []
    for name in names:
        if not FILENAME_RE.match(name):
            all_findings.append({"file": name, "rule": "filename", "line": 0,
                                 "severity": "error",
                                 "msg": "must match NNNN_snake_name.sql (4 digits, snake_case)"})
            continue
        prefix = name.split("_", 1)[0]
        if prefix in prefixes:
            all_findings.append({"file": name, "rule": "prefix-collision", "line": 0,
                                 "severity": "error",
                                 "msg": f"prefix {prefix} already used by {prefixes[prefix]}"})
        prefixes[prefix] = name
        with open(os.path.join(path, name), encoding="utf-8") as fh:
            text = fh.read()
        for f in lint_text(text):
            all_findings.append({"file": name, **f})
    err_count = sum(1 for f in all_findings if f["severity"] == "error")
    return {
        "files": len(names), "findings": all_findings,
        "errors": errors, "error_count": err_count,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Forward-only SQL migration lint")
    ap.add_argument("dir", nargs="?", default=DEFAULT_DIR,
                    help="migrations dir (default db/migrations)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    result = lint_dir(args.dir)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"migration-lint: {result['files']} file(s) in {args.dir}")
        for f in result["findings"]:
            print(f"  {f['severity'].upper():7} {f['file']}:{f['line']} [{f['rule']}] {f['msg']}")
        for e in result["errors"]:
            print(f"  ERROR   {e}")
        print(f"migration-lint: {result.get('error_count', 0)} error(s)")
    return 1 if (result.get("error_count") or result["errors"]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
