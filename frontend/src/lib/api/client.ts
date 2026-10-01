// Typed fetch client — frontend reaches the API only (never DB, never env
// secrets). Response shapes are validated against the generated zod mirror of
// the pydantic contract (src/lib/contract/contract.ts, ADR 0003).
import { z } from "zod";

import { HealthResponseSchema } from "../contract/contract";

const API_BASE = "/v1";

async function getJson(path: string): Promise<unknown> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { accept: "application/json" } });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json();
}

export async function getHealth(): Promise<z.infer<typeof HealthResponseSchema>> {
  // /healthz lives at root (deploy smoke contract), not under /v1.
  const res = await fetch("/healthz", { headers: { accept: "application/json" } });
  if (!res.ok) throw new Error(`GET /healthz -> ${res.status}`);
  return HealthResponseSchema.parse(await res.json());
}

export const api = { getJson, getHealth };
