"""API request/response contract — pydantic models = THE single contract.

Per ADR 0003 decision 4, exactly one contract exists: these pydantic models.
The Zod mirror for the frontend is GENERATED from this module by
`scripts/contract_sync.py` into `frontend/src/lib/contract/contract.ts` —
never hand-edit the generated file, never hand-mirror a model.

Scaffold scope (card E1.1): health/readiness + one domain model (GammaNode)
that exercises the generator subset (enums, floats, optional/nullable).
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Base for all API contract models: no silent extra keys (aligns pydantic
    `extra=forbid` with the generated zod `.strict()`)."""

    model_config = ConfigDict(extra="forbid")


class NodeClassification(str, Enum):
    """Node classification taxonomy (docs/build/e05b-king-parity.md)."""

    king = "king"
    wall = "wall"
    gatekeeper = "gatekeeper"
    significant = "significant"
    normal = "normal"


class HealthResponse(ContractModel):
    """GET /healthz — process liveness."""

    status: Literal["ok"]
    version: str


class ReadyCheck(ContractModel):
    """One dependency check behind GET /readyz."""

    name: str
    ok: bool
    detail: Optional[str] = None


class ReadyResponse(ContractModel):
    """GET /readyz — DB + data-source readiness with payload freshness."""

    status: Literal["ready", "degraded"]
    checks: list[ReadyCheck]
    last_payload_age_s: Optional[float] = None


class GammaNode(ContractModel):
    """One strike node on the exposure grid (contract skeleton — E1.1).

    `value` is the node value V(s,t) from backend/core/exposure.py;
    `net_gex` is the within-expiry call_gex − put_gex (spec §2).
    """

    strike: float
    expiry_date: str
    net_gex: float
    value: float
    classification: NodeClassification
