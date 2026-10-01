#!/usr/bin/env python3
"""Build data/e05b/before_after_report.{json,md} from harness summaries."""
import json, os, datetime
REPO = "/Users/admin/Desktop/Github-Projects/gammasummit"
BASE = os.path.join(REPO, "data", "e05b")

def load(name):
    return json.load(open(os.path.join(BASE, name, "summary.json")))

before = load("before")
after = load("after")
after_state = None
if os.path.exists(os.path.join(BASE, "after_state", "summary.json")):
    after_state = load("after_state")

rows = []
def row(label, b, a, s):
    return {"metric": label, "before_gamma1": b, "after_gamma07": a,
            "after_state_layer": s}

bo, ao = before["overall"], after["overall"]
so = after_state["overall"] if after_state else None
rows.append(row("king_exact_rate", bo["king_exact_rate"], ao["king_exact_rate"],
                so["king_exact_rate"] if so else None))
rows.append(row("king_within_tol_rate", bo["king_within_tol_rate"], ao["king_within_tol_rate"],
                so["king_within_tol_rate"] if so else None))
rows.append(row("top6_overlap_mean", bo["top6_overlap_mean"], ao["top6_overlap_mean"],
                so["top6_overlap_mean"] if so else None))
rows.append(row("global_star_exact_rate", bo["global_star_exact_rate"], ao["global_star_exact_rate"],
                so["global_star_exact_rate"] if so else None))

per_symbol = {}
for sym in sorted({*before.get("per_symbol", {}), *after.get("per_symbol", {})} | set()):
    pass
# harness summary has no per_symbol; compute from per_record.csv
import csv
from collections import defaultdict
def per_sym_day(name):
    out = defaultdict(lambda: {"n": 0, "exact": 0, "tol": 0})
    with open(os.path.join(BASE, name, "per_record.csv")) as f:
        for r in csv.DictReader(f):
            for key in (r["symbol"], r["day"]):
                slot = out[key]
                slot["n"] += 1
                slot["exact"] += r["king_exact"] == "True"
                slot["tol"] += r["king_within_tol"] == "True"
    return {k: {"n": v["n"], "exact_rate": round(v["exact"]/v["n"], 4),
                "tol_rate": round(v["tol"]/v["n"], 4)} for k, v in sorted(out.items())}

report = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "script": "scripts/e05b_report.py",
    "dataset": "data/e02/fit_dataset (post-refresh 2026-10-01), 1691 records, 2026-09-28/29/30",
    "models": {
        "before_gamma1": "E0.3 baseline (psi gamma=1.0) -- data/e05b/before",
        "after_gamma07": "E0.5b correction (psi gamma=0.7, spec 12) -- data/e05b/after",
        "after_state_layer": "E0.5b correction + E0.5a state layer -- data/e05b/after_state",
    },
    "overall": rows,
    "per_symbol_before": per_sym_day("before"),
    "per_symbol_after": per_sym_day("after"),
    "per_day_before": {k: v for k, v in per_sym_day("before").items() if k.startswith("2026-")},
    "per_day_after": {k: v for k, v in per_sym_day("after").items() if k.startswith("2026-")},
    "run_commands": [
        "python3 scripts/e05b_flip_taxonomy.py taxonomy --gamma 1.0   # taxonomy on the baseline",
        "python3 scripts/e05b_king_fix.py sweep --out data/e05b/sweep.json",
        "python3 scripts/e03_batch_harness.py run --execute --out-dir data/e05b/before   # (pre-patch; re-run: --gamma 1.0 -> data/e05b/before_g1_check, exact match)",
        "python3 scripts/e03_batch_harness.py run --execute --out-dir data/e05b/after",
        "python3 scripts/e03_batch_harness.py run --execute --state-layer --out-dir data/e05b/after_state",
        "python3 scripts/e03_batch_harness.py verify --out-dir data/e05b/after",
        "python3 -m unittest discover -s backend/tests",
    ],
}
if after_state:
    report["per_symbol_after_state"] = per_sym_day("after_state")
    report["per_day_after_state"] = {k: v for k, v in per_sym_day("after_state").items() if k.startswith("2026-")}

if so:
    s_exact = f"{so['king_exact_rate']:.2%}"
    s_tol = f"{so['king_within_tol_rate']:.2%}"
    s_top6 = f"{so['top6_overlap_mean']}"
    s_star = f"{so['global_star_exact_rate']:.2%}"
else:
    s_exact = s_tol = s_top6 = s_star = "n/a"

out_json = os.path.join(BASE, "before_after_report.json")
json.dump(report, open(out_json, "w"), indent=1)

def fmt(d):
    return "\n".join(f"| {k} | {v['n']} | {v['exact_rate']:.2%} | {v['tol_rate']:.2%} |" for k, v in d.items())

md = f"""# E0.5b king-parity before/after report

Generated: {report['generated_at']} · script `scripts/e05b_report.py`

Dataset: {report['dataset']}

| metric | before (gamma=1.0) | after (gamma=0.7) | after + state layer |
|---|---|---|---|
| king exact | {bo['king_exact_rate']:.2%} | {ao['king_exact_rate']:.2%} | {s_exact} |
| king within tol | {bo['king_within_tol_rate']:.2%} | {ao['king_within_tol_rate']:.2%} | {s_tol} |
| top6 overlap | {bo['top6_overlap_mean']} | {ao['top6_overlap_mean']} | {s_top6} |
| global star exact | {bo['global_star_exact_rate']:.2%} | {ao['global_star_exact_rate']:.2%} | {s_star} |

Per symbol (king exact / within tol):

| symbol | n | before exact | before tol | after exact | after tol |
|---|---|---|---|---|---|
"""
for sym in sorted(k for k in report["per_symbol_before"] if not k.startswith("2026-")):
    b, a = report["per_symbol_before"][sym], report["per_symbol_after"][sym]
    md += f"| {sym} | {b['n']} | {b['exact_rate']:.2%} | {b['tol_rate']:.2%} | {a['exact_rate']:.2%} | {a['tol_rate']:.2%} |\n"
md += "\nPer day:\n\n| day | n | before exact | before tol | after exact | after tol |\n|---|---|---|---|---|---|\n"
for day in sorted(report["per_day_before"]):
    b, a = report["per_day_before"][day], report["per_day_after"][day]
    md += f"| {day} | {b['n']} | {b['exact_rate']:.2%} | {b['tol_rate']:.2%} | {a['exact_rate']:.2%} | {a['tol_rate']:.2%} |\n"
md += """
Run commands (every number traceable):

""" + "\n".join(f"- `{c}`" for c in report["run_commands"]) + """

Honest note: the >=90% king-exact gate bar is NOT met on these 3 Tier-A days
(pilot-grade; gate re-measure over >=20 session-days by card t_b157a485,
~2026-10-28). The value-faithful oracle bound (hindsight per-record joint LS
weights on the established g basis) is 68.6% exact -- see
docs/build/e05b-king-parity.md section 5.
"""
out_md = os.path.join(BASE, "before_after_report.md")
open(out_md, "w").write(md)
print("wrote", out_json)
print("wrote", out_md)
