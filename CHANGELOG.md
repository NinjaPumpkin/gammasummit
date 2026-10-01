# Changelog

All notable changes to this project are documented in this file (Keep a
Changelog). Versioning scheme: `docs/build/code-structure-and-release.md` §4 —
SemVer app tags `v0.x` pre-cutover, `v1.0.0` at cutover.

## [Unreleased]

### Added

- E1.1 scaffold: code tree (`backend/`, `db/`, `frontend/`, `deploy/`), manifests
  (`pyproject.toml`, root `package.json` workspace, `.env.example` with
  `GAMMASUMMIT_*` placeholders only, `AGENTS.md`), FastAPI app skeleton
  (`/healthz`, `/readyz`), migration lint harness (`scripts/migration_lint.py`),
  Zod<->pydantic single-contract skeleton (`scripts/contract_sync.py`, ADR 0003),
  Vite+React frontend placeholder wired to `frontend/mockups/`, deploy
  placeholders (systemd units, docker compose, VPS release scripts), scaffold
  smoke tests.
