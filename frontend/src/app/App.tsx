// Placeholder shell (card E1.1 scaffold). The real Parity Shell (34-point
// checklist: docs/build/parity-checklist-skylit.md) lands with workstream F;
// this screen only wires the app to the approved reference visual in
// frontend/mockups/dashboard-v3.html (served at /mockups/ in dev).
import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";

import { getHealth } from "../lib/api/client";

const shell: CSSProperties = {
  fontFamily: "ui-sans-serif, system-ui, sans-serif",
  padding: "24px",
  maxWidth: "1200px",
  margin: "0 auto",
};

const frame: CSSProperties = {
  width: "100%",
  height: "560px",
  border: "1px solid #232a38",
  borderRadius: "8px",
  background: "#0f131c",
};

export function App() {
  const health = useQuery({ queryKey: ["healthz"], queryFn: getHealth, retry: 1 });

  return (
    <div style={shell}>
      <h1 style={{ marginTop: 0 }}>GammaSummit</h1>
      <p style={{ color: "#9aa4b5" }}>
        Scaffold placeholder — parity shell lands per{" "}
        <code>docs/build/parity-checklist-skylit.md</code>. API health:{" "}
        <strong>{health.data ? `${health.data.status} (v${health.data.version})` : health.isError ? "unreachable" : "checking…"}</strong>
      </p>
      <h2 style={{ fontSize: "16px" }}>Approved reference visual</h2>
      <iframe title="dashboard-v3 mockup" src="/mockups/dashboard-v3.html" style={frame} />
    </div>
  );
}
