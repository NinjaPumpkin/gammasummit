#!/usr/bin/env python3
"""e24_kuma_admin.py — Uptime Kuma alarm wiring for the freshness metric (E2.4).

Self-hosted Uptime Kuma (docs/ops/operations.md "Freshness = health") gets one
PUSH monitor per freshness check plus a webhook notification channel:

  gs-freshness-overall    -> GAMMASUMMIT_KUMA_PUSH_OVERALL
  gs-t0-freshness         -> GAMMASUMMIT_KUMA_PUSH_T0_FRESHNESS
  gs-downsampler-lag      -> GAMMASUMMIT_KUMA_PUSH_DOWNSAMPLER_LAG
  gs-retention-jobs       -> GAMMASUMMIT_KUMA_PUSH_RETENTION_JOBS

`backend/jobs/freshness.py --push` beacons each verdict to its monitor URL; a
down verdict flips the monitor and its notification channel FIRES. A silent
job (no beacon at all) is caught by the push heartbeat age.

Secrets discipline: the push URLs embed push tokens and the Kuma admin
password is generated locally — both go to `.env` (gitignored) and are NEVER
printed. This script prints only monitor names/ids.

Ops-only dependency (not a repo dependency): uptime-kuma-api
  python3 -m pip install uptime-kuma-api   (or a dedicated ops venv)

CLI:
  python3 scripts/e24_kuma_admin.py wire --webhook-url http://127.0.0.1:8787/
  python3 scripts/e24_kuma_admin.py evidence --out data/e24_kuma/heartbeats.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

BASE_URL_DEFAULT = "http://127.0.0.1:3001"
KUMA_USER = "admin"
DATA_DIR = os.path.join(REPO, "data", "e24_kuma")
ENV_PATH = os.path.join(REPO, ".env")
PUSH_URLS_JSON = os.path.join(DATA_DIR, "push_urls.json")

MONITORS = (
    ("gs-freshness-overall", "overall"),
    ("gs-t0-freshness", "t0_freshness"),
    ("gs-downsampler-lag", "downsampler_lag"),
    ("gs-retention-jobs", "retention_jobs"),
)
ENV_KEYS = {
    "overall": "GAMMASUMMIT_KUMA_PUSH_OVERALL",
    "t0_freshness": "GAMMASUMMIT_KUMA_PUSH_T0_FRESHNESS",
    "downsampler_lag": "GAMMASUMMIT_KUMA_PUSH_DOWNSAMPLER_LAG",
    "retention_jobs": "GAMMASUMMIT_KUMA_PUSH_RETENTION_JOBS",
}
PASSWORD_KEY = "GAMMASUMMIT_KUMA_ADMIN_PASSWORD"


def _kuma_api():
    try:
        from uptime_kuma_api import MonitorType, NotificationType, UptimeKumaApi  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover — ops environment check
        raise SystemExit(
            "uptime-kuma-api is required for this ops tool (NOT a repo dependency):\n"
            "  python3 -m pip install uptime-kuma-api"
        ) from exc
    return UptimeKumaApi, MonitorType, NotificationType


def _env_write(updates: dict[str, str]) -> None:
    """Merge keys into .env without printing values (gitignored, secret-safe)."""
    lines: list[str] = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as fh:
            lines = fh.read().splitlines()
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    with open(ENV_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def _admin_password() -> str:
    existing = os.environ.get(PASSWORD_KEY)
    if existing:
        return existing
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as fh:
            for line in fh:
                if line.startswith(PASSWORD_KEY + "="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        return value
    value = secrets.token_urlsafe(24)
    _env_write({PASSWORD_KEY: value})
    return value


def cmd_wire(args: argparse.Namespace) -> int:
    UptimeKumaApi, MonitorType, NotificationType = _kuma_api()
    api = UptimeKumaApi(args.base_url, timeout=20)
    try:
        try:
            if api.need_setup():
                api.setup(KUMA_USER, _admin_password())
            else:
                api.login(KUMA_USER, _admin_password())
        except Exception:  # noqa: BLE001 — wrong password should fail loudly but cleanly
            api.login(KUMA_USER, _admin_password())

        # notification channel (idempotent by name). The notificationList
        # event can lag right after first-run setup — retry once before acting.
        note_id = None
        notes = []
        for attempt in (1, 2):
            try:
                notes = api.get_notifications() or []
                break
            except Exception:  # noqa: BLE001 — event-timing race, not a hard failure
                if attempt == 2:
                    raise
                import time  # noqa: PLC0415
                time.sleep(3)
        for n in notes:
            if n.get("name") == "gs-freshness-alarms":
                note_id = n["id"]
                break
        if note_id is None:
            note = api.add_notification(
                name="gs-freshness-alarms",
                type=NotificationType.WEBHOOK,
                webhookURL=args.webhook_url,
                webhookContentType="application/json",
            )
            note_id = note["id"]
        else:
            # keep the channel pointed at the current webhook (re-wire runs)
            api.edit_notification(
                note_id,
                name="gs-freshness-alarms",
                type=NotificationType.WEBHOOK,
                webhookURL=args.webhook_url,
                webhookContentType="application/json",
            )

        # push monitors (idempotent by name), each attached to the channel
        existing = {m.get("name"): m for m in (api.get_monitors() or [])}
        push_urls: dict[str, str] = {}
        for name, check_id in MONITORS:
            if name not in existing:
                api.add_monitor(
                    type=MonitorType.PUSH,
                    name=name,
                    description=f"freshness check `{check_id}` beacon (backend/jobs/freshness.py --push)",
                    interval=args.heartbeat_interval,
                    maxretries=1,
                    notificationIDList=[note_id],
                )
            # resolve by name (add_monitor's return shape varies by version;
            # the monitor list is the source of truth)
            monitor = next((m for m in (api.get_monitors() or []) if m.get("name") == name), None)
            if monitor is None:
                print(f"monitor {name} was not created — cannot wire beacon", file=sys.stderr)
                return 1
            token = monitor.get("pushToken")
            if not token:
                print(f"monitor {name} has no pushToken — cannot wire beacon", file=sys.stderr)
                return 1
            push_urls[check_id] = f"{args.base_url}/api/push/{token}"

        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PUSH_URLS_JSON, "w", encoding="utf-8") as fh:
            json.dump({"base_url": args.base_url,
                       "note": "SECRET: push tokens — do not commit (data/ is gitignored)",
                       "urls": push_urls}, fh, indent=1)
        _env_write({ENV_KEYS[c]: u for c, u in push_urls.items()})
        print(json.dumps({"wired": [m[0] for m in MONITORS],
                          "notification": "gs-freshness-alarms",
                          "push_urls_saved_to": [".env", PUSH_URLS_JSON],
                          "password_saved_to": ".env"}, indent=1))
        return 0
    finally:
        api.disconnect()


def cmd_evidence(args: argparse.Namespace) -> int:
    UptimeKumaApi, _MonitorType, _NotificationType = _kuma_api()
    api = UptimeKumaApi(args.base_url, timeout=20)
    try:
        api.login(KUMA_USER, _admin_password())
        out = {"captured_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(), "monitors": {}}
        for name, check_id in MONITORS:
            monitor = next((m for m in (api.get_monitors() or []) if m.get("name") == name), None)
            if monitor is None:
                out["monitors"][name] = {"missing": True}
                continue
            beats = api.get_monitor_beats(monitor["id"], hours=24) or []
            out["monitors"][name] = {
                "check_id": check_id,
                "monitor_id": monitor["id"],
                "status": monitor.get("status"),
                "beats": [
                    {"time": str(b.get("time")), "status": b.get("status"),
                     "msg": b.get("msg"), "important": bool(b.get("important"))}
                    for b in beats
                ],
            }
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        print(json.dumps({"saved": args.out,
                          "beat_counts": {n: len(m.get("beats", []))
                                          for n, m in out["monitors"].items()}}, indent=1))
        return 0
    finally:
        api.disconnect()


def cmd_test_notification(args: argparse.Namespace) -> int:
    """Send a test webhook — the runbook's channel-verify step."""
    UptimeKumaApi, _MonitorType, NotificationType = _kuma_api()
    api = UptimeKumaApi(args.base_url, timeout=20)
    try:
        api.login(KUMA_USER, _admin_password())
        note = next((n for n in (api.get_notifications() or [])
                     if n.get("name") == "gs-freshness-alarms"), None)
        if note is None:
            print("notification gs-freshness-alarms not found — run `wire` first", file=sys.stderr)
            return 1
        cfg = note.get("config", {})
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        opts = {k: v for k, v in cfg.items()
                if k in ("webhookURL", "webhookContentType",
                         "webhookCustomBody", "webhookAdditionalHeaders")}
        if not opts.get("webhookURL"):
            if not args.webhook_url:
                print("notification config carries no webhookURL — pass --webhook-url", file=sys.stderr)
                return 1
            opts["webhookURL"] = args.webhook_url
        opts.setdefault("webhookContentType", "application/json")
        result = api.test_notification(
            name="gs-freshness-alarms", type=NotificationType.WEBHOOK, **opts)
        print(json.dumps({"test_notification": str(result)[:200]}, indent=1))
        return 0
    finally:
        api.disconnect()


def main() -> int:
    ap = argparse.ArgumentParser(description="Uptime Kuma wiring + evidence (E2.4)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    wire = sub.add_parser("wire", help="create notification + push monitors, save beacon URLs")
    wire.add_argument("--base-url", default=BASE_URL_DEFAULT)
    wire.add_argument("--webhook-url", required=True, help="where Kuma POSTs alarm/recovery webhooks")
    wire.add_argument("--heartbeat-interval", type=int, default=86400,
                      help="expected beacon gap in seconds (prod systemd timer = 300)")
    wire.set_defaults(func=cmd_wire)
    ev = sub.add_parser("evidence", help="capture monitor state + heartbeat history")
    ev.add_argument("--base-url", default=BASE_URL_DEFAULT)
    ev.add_argument("--out", required=True)
    ev.set_defaults(func=cmd_evidence)
    test = sub.add_parser("test", help="send a test webhook to verify the notification channel")
    test.add_argument("--base-url", default=BASE_URL_DEFAULT)
    test.add_argument("--webhook-url", default="",
                      help="channel URL fallback when the stored config omits it")
    test.set_defaults(func=cmd_test_notification)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
