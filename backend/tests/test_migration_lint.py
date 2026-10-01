"""Unit tests for scripts/migration_lint.py (card E1.1).

Covers every rule plus the false-positive traps (comments, string literals,
dollar-quoted bodies) and the repo's real db/migrations dir.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts import migration_lint as ml  # noqa: E402


def rules(findings):
    return sorted(f["rule"] for f in findings)


class RulesTest(unittest.TestCase):
    def test_clean_migration(self):
        sql = """
        CREATE TABLE t (id BIGINT PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now());
        INSERT INTO t (id) VALUES (1);
        UPDATE t SET ts = now() WHERE id = 1;
        DELETE FROM t WHERE id = 1;
        """
        self.assertEqual(ml.lint_text(sql), [])

    def test_drop_table_flagged(self):
        findings = ml.lint_text("DROP TABLE old_t;")
        self.assertEqual(rules(findings), ["destructive-ddl"])

    def test_drop_column_multiline_flagged(self):
        findings = ml.lint_text("ALTER TABLE t\n  DROP COLUMN legacy;")
        self.assertEqual(rules(findings), ["destructive-ddl"])

    def test_truncate_flagged(self):
        self.assertEqual(rules(ml.lint_text("TRUNCATE t;")), ["destructive-ddl"])

    def test_unflagged_dml(self):
        self.assertEqual(rules(ml.lint_text("UPDATE t SET a = 1;")), ["unguarded-dml"])
        self.assertEqual(rules(ml.lint_text("DELETE FROM t;")), ["unguarded-dml"])

    def test_grants_flagged(self):
        self.assertEqual(rules(ml.lint_text("GRANT ALL ON t TO app;")), ["deny-default-grant"])
        grant_public = ml.lint_text("GRANT SELECT ON t TO PUBLIC;")
        self.assertEqual(rules(grant_public), ["deny-default-grant"])

    def test_txn_control_flagged(self):
        self.assertEqual(rules(ml.lint_text("BEGIN; COMMIT;")), ["txn-control", "txn-control"])

    def test_comments_not_flagged(self):
        sql = "-- DROP TABLE t; also GRANT ALL and TRUNCATE\nCREATE TABLE t (id INT);"
        self.assertEqual(ml.lint_text(sql), [])

    def test_string_literal_not_flagged(self):
        sql = "INSERT INTO t (id, note) VALUES (1, 'DROP TABLE nope; TRUNCATE nope');"
        self.assertEqual(ml.lint_text(sql), [])

    def test_function_body_not_flagged_for_txn(self):
        sql = """
        CREATE FUNCTION f() RETURNS int AS $$
        BEGIN
          RETURN 1;
        END;
        $$ LANGUAGE plpgsql;
        """
        self.assertEqual(ml.lint_text(sql), [])

    def test_destructive_inside_function_body_still_flagged(self):
        sql = """
        CREATE FUNCTION f() RETURNS void AS $$
        BEGIN
          DROP TABLE audit_scratch;
        END;
        $$ LANGUAGE plpgsql;
        """
        self.assertEqual(rules(ml.lint_text(sql)), ["destructive-ddl"])

    def test_allow_marker_downgrades(self):
        sql = "-- migration-lint: allow destructive\nDROP TABLE old_t;"
        findings = ml.lint_text(sql)
        self.assertEqual(rules(findings), ["destructive-ddl"])
        self.assertEqual(findings[0]["severity"], "warning")

    def test_empty_migration(self):
        self.assertEqual(rules(ml.lint_text("-- only a comment")), ["empty-migration"])


class DirTest(unittest.TestCase):
    def test_filename_and_prefix_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("0001_ok.sql", "0001_dup.sql", "bad-name.sql"):
                with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                    fh.write("CREATE TABLE t (id INT);")
            result = ml.lint_dir(tmp)
            found = rules(result["findings"])
            self.assertIn("filename", found)
            self.assertIn("prefix-collision", found)

    def test_repo_migrations_clean(self):
        result = ml.lint_dir(os.path.join(REPO, "db", "migrations"))
        self.assertGreaterEqual(result["files"], 1)
        self.assertEqual(result["error_count"], 0, result["findings"])


if __name__ == "__main__":
    unittest.main()
