#!/usr/bin/env python3
"""Summarize fit_results.json: column quality, baselines, sign stats, dynamic stage."""
import json
import statistics

res = json.load(open("/Users/admin/Desktop/Github-Projects/gammasummit/data/e02/fit_results.json"))
print("n_instants:", res["n_instants"])
pi = res["per_instant"]
med_rho = statistics.median([i["col_quality"]["median_rho"] for i in pi])
med_r2 = statistics.median([i["col_quality"]["median_col_r2"] for i in pi])
ncols = statistics.median([i["col_quality"]["n_cols_fit"] for i in pi])
print("median per-instant: cols_fit", ncols, "| col median_rho", round(med_rho, 4),
      "| col median_r2", round(med_r2, 4))
# baseline sse ratios
for b in ("H0-uniform", "H1-dte-power", "H2-colmag"):
    vals = [i["baselines"].get(b, {}).get("sse_ratio") for i in pi
            if i["baselines"].get(b, {}).get("sse_ratio") is not None]
    if vals:
        vals.sort()
        print(f"{b}: sse_ratio median {round(vals[len(vals)//2], 4)} p25 {round(vals[len(vals)//4], 4)} p75 {round(vals[3*len(vals)//4], 4)}")
betas = [i["baselines"]["H1-dte-power"]["beta"] for i in pi if "H1-dte-power" in i["baselines"]]
if betas:
    betas.sort()
    print("H1 beta median:", betas[len(betas)//2], "p25", betas[len(betas)//4], "p75", betas[3*len(betas)//4])
gammas = [i["baselines"]["H2-colmag"]["gamma"] for i in pi if "H2-colmag" in i["baselines"]]
if gammas:
    gammas.sort()
    print("H2 gamma median:", round(gammas[len(gammas)//2], 2), "p25", round(gammas[len(gammas)//4], 2),
          "p75", round(gammas[3*len(gammas)//4], 2))
print("sign_stats:", res.get("sign_stats"))
fm = res.get("feature_model", {})
print("feature_model: r2_log_abs_a", fm.get("r2_log_abs_a"),
      "sign_agreement", fm.get("sign_agreement_vs_netcol"),
      "a_positive_share", fm.get("a_positive_share"))
print("theta:", fm.get("theta"))
print("LOTO:", json.dumps(fm.get("leave_one_day_out", {}), indent=1))
dyn = res.get("dynamic", {})
print("dynamic keys:", list(dyn.keys()))
if "error" in dyn:
    print("DYNAMIC ERROR:", dyn["error"])
else:
    print("windows:", dyn.get("windows_processed"), "frames:", dyn.get("frames_processed"))
    print("notes:", dyn.get("notes"))
    for day, s in dyn.get("per_day", {}).items():
        print(day, "windows", s["windows"], "frames", s["frames"],
              "emp_r2_median", s["emp_r2_median"], "ewma:", json.dumps(s.get("ewma", {})))
