"""Multi-sample re-run: single-shot results are NOT trustworthy here.

WHY THIS EXISTS: the same arm (1.5B + legacy retry) produced cross_source 0.0 /
combine verbatim 0.678 on one run and cross_source 1.0 / verbatim 0.105 on the next.
Sampling noise at temperature 0.2 is large enough to flip every conclusion, so any
single-shot comparison is worthless. This script runs the same arm N times and reports
the distribution instead of a point estimate.

Only the COMBINE operator is sampled — it is where the interesting failures live
(cross-source synthesis), and it is the expensive part.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import corpus
from quality_rubric import score_artifact, verdict
from rerun import make_client, run_combine, BASELINE_MODEL, ITER_MODEL, TARGET_MODEL

MODELS = {
    "1.5b": BASELINE_MODEL,
    "4b": ITER_MODEL,
    "9b": TARGET_MODEL,
}


def sample(model_key: str, n: int, policy: str = "resilient") -> dict:
    client = make_client("json")
    model = MODELS[model_key]
    rows = []
    for i in range(n):
        try:
            out = run_combine(client, model, policy, corpus.QUERY, corpus.SOURCES)
        except Exception as e:  # noqa: BLE001
            rows.append({"error": f"{type(e).__name__}: {e}"})
            print(f"  [{model_key} {i+1}/{n}] ERROR", file=sys.stderr)
            continue
        if "error" in out:
            rows.append({"error": out["error"]})
            print(f"  [{model_key} {i+1}/{n}] rejected: {out['error'][:60]}", file=sys.stderr)
            continue
        s = score_artifact(out["artifact"], corpus.SOURCES)
        v = verdict(s, "artifact")
        rows.append({"scores": s, "pass": v["all_pass"]})
        print(f"  [{model_key} {i+1}/{n}] n={s['n_claims']} ncross={s['n_cross_source']} "
              f"rate={s['cross_source_rate']} v={s['verbatim_rate']} pass={v['all_pass']}",
              file=sys.stderr)

    ok = [r for r in rows if "scores" in r]
    def _col(name):
        vals = [r["scores"][name] for r in ok if r["scores"].get(name) is not None]
        return vals

    summary = {"model": model_key, "policy": policy, "n_requested": n, "n_ok": len(ok),
               "errors": [r.get("error") for r in rows if "error" in r],
               "pass_count": sum(1 for r in ok if r["pass"])}
    for name in ("verbatim_rate", "overlap", "cross_source_rate", "n_claims",
                 "n_cross_source", "citation_hit"):
        vals = _col(name)
        if vals:
            summary[name] = {
                "values": vals,
                "median": round(statistics.median(vals), 3),
                "min": round(min(vals), 3), "max": round(max(vals), 3),
            }
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="1.5b,4b")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--out", default="multisample.json")
    args = ap.parse_args()

    out = {}
    for key in args.models.split(","):
        print(f"--- sampling {key} x{args.n} ---", file=sys.stderr)
        out[key] = sample(key, args.n)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    print(f"\n{'model':8} {'pass':6} {'verbatim(med/min/max)':26} {'cross_rate':22} {'n_claims':16}")
    for k, v in out.items():
        vb = v.get("verbatim_rate", {})
        cr = v.get("cross_source_rate", {})
        nc = v.get("n_claims", {})
        print(f"{k:8} {v['pass_count']}/{v['n_ok']:<4} "
              f"{str((vb.get('median'), vb.get('min'), vb.get('max'))):26} "
              f"{str((cr.get('median'), cr.get('min'), cr.get('max'))):22} "
              f"{str((nc.get('median'), nc.get('min'), nc.get('max'))):16}")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
