"""Scaffold smoke tests (card E1.1).

Acceptance evidence for the scaffold: app factory answers, settings follow the
GAMMASUMMIT_* law, `.env.example` holds placeholders only, and AGENTS.md is a
verbatim copy of docs/build/README.md (the builder guide).
"""
from __future__ import annotations

import os
import re
import unittest

from fastapi.testclient import TestClient

from backend.api.deps import Settings
from backend.api.main import APP_VERSION, create_app

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _offline_app():
    """App with explicit settings — never touches real env/DB/network."""
    return create_app(Settings(database_url=None))


class HealthTest(unittest.TestCase):
    def test_healthz(self):
        client = TestClient(_offline_app())
        res = client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "version": APP_VERSION})

    def test_request_id_header(self):
        client = TestClient(_offline_app())
        res = client.get("/healthz", headers={"x-request-id": "test-req-1"})
        self.assertEqual(res.headers.get("x-request-id"), "test-req-1")
        res = client.get("/healthz")
        self.assertTrue(res.headers.get("x-request-id"))  # generated when absent

    def test_readyz_degraded_without_db(self):
        client = TestClient(_offline_app())
        res = client.get("/readyz")
        self.assertEqual(res.status_code, 503)
        body = res.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["checks"][0]["name"], "db")
        self.assertFalse(body["checks"][0]["ok"])


class SettingsLawTest(unittest.TestCase):
    def test_env_prefix(self):
        os.environ["GAMMASUMMIT_LOG_LEVEL"] = "DEBUG"
        try:
            cfg = Settings(_env_file=None, database_url=None)
            self.assertEqual(cfg.log_level, "DEBUG")
        finally:
            del os.environ["GAMMASUMMIT_LOG_LEVEL"]

    def test_feature_flags_default_off(self):
        cfg = Settings(_env_file=None, database_url=None)
        self.assertFalse(cfg.ff_analyst)
        self.assertFalse(cfg.ff_exec_gate)
        self.assertFalse(cfg.ff_nexus)


class ManifestAcceptanceTest(unittest.TestCase):
    """Acceptance: .env.example contains placeholders only."""

    def test_env_example_placeholders_only(self):
        path = os.path.join(REPO, ".env.example")
        with open(path, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip() and not ln.strip().startswith("#")]
        self.assertTrue(lines, ".env.example has no keys")
        for ln in lines:
            self.assertRegex(ln, r"^GAMMASUMMIT_[A-Z0-9_]+=$", f"non-placeholder line: {ln!r}")
            self.assertFalse(re.search(r"[A-Za-z0-9]{8,}=$", ln), f"value present: {ln!r}")

    def test_agents_md_is_builder_guide_copy(self):
        with open(os.path.join(REPO, "AGENTS.md"), encoding="utf-8") as fh:
            agents = fh.read()
        with open(os.path.join(REPO, "docs", "build", "README.md"), encoding="utf-8") as fh:
            guide = fh.read()
        self.assertEqual(agents, guide)

    def test_env_example_documents_every_settings_key(self):
        """Every Settings field must have a GAMMASUMMIT_* line in .env.example."""
        with open(os.path.join(REPO, ".env.example"), encoding="utf-8") as fh:
            content = fh.read()
        for name in Settings.model_fields:
            key = f"GAMMASUMMIT_{name.upper()}="
            self.assertIn(key, content, f"missing key for setting {name}")


if __name__ == "__main__":
    unittest.main()
