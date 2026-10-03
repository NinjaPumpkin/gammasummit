#!/usr/bin/env python3
"""e24_kuma_sink.py — local webhook sink for Uptime Kuma alarm evidence (E2.4).

Kuma's `gs-freshness-alarms` webhook notification POSTs here on every state
transition (alarm DOWN and recovery UP). Each POST lands as one JSON line —
the durable evidence that an alarm actually FIRED and then CLEARED. In
production this channel points at the real ops endpoint (telegram/email
bridge); the sink is the local proof harness.

Stdlib only. CLI:
  python3 scripts/e24_kuma_sink.py --port 8787 --out data/e24_kuma/alarms.jsonl
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = "data/e24_kuma/alarms.jsonl"


class Handler(BaseHTTPRequestHandler):
    out_path: str = OUT

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"raw": raw[:2000]}
        record = {"received_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(), "body": body}
        os.makedirs(os.path.dirname(self.out_path) or ".", exist_ok=True)
        with open(self.out_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *args, **kwargs):  # quiet
        return


def main() -> int:
    ap = argparse.ArgumentParser(description="Uptime Kuma webhook sink (alarm evidence)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (0.0.0.0 when Kuma runs in Docker and calls host.docker.internal)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    Handler.out_path = args.out
    server = HTTPServer((args.host, args.port), Handler)
    print(f"kuma sink listening on {args.host}:{args.port} -> {args.out}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
