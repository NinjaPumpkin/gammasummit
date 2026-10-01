#!/usr/bin/env python3
"""Final numbers: EWMA lambda grid + joint per-day metrics from fit_results.json."""
import json

res = json.load(open("/Users/admin/Desktop/Github-Projects/gammasummit/data/e02/fit_results.json"))
print("=== per_day (incl joint) ===")
for day, s in res["per_day"].items():
    print(day, json.dumps(s))
print("\n=== EWMA (dynamic) ===")
for day, s in res["dynamic"]["per_day"].items():
    for sym, e in s.get("ewma", {}).items():
        grid = e.get("mse_grid", {})
        gshort = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in list(grid.items())}
        print(day, sym, "lambda:", e.get("lambda"), "mse:", e.get("mse"),
              "n:", e.get("n_traj_points"), "grid:", gshort)
