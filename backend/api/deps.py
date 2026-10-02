"""Settings + dependency wiring for the API layer (tree: api/deps.py).

Config law (docs/build/code-structure-and-release.md §3): settings via
pydantic-settings, env prefix `GAMMASUMMIT_`; `.env` gitignored;
`.env.example` documents every key — keep the two in sync (scaffold test
enforces it).

Since card E2.1 the definitions live in `backend.core.config` (the spine every
module imports — ultraplan P1); this module re-exports them so the API layer
keeps its documented import surface.
"""
from __future__ import annotations

from backend.core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
