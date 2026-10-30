"""Spike 11 multi-sample: operator fix is a DISTRIBUTION claim, not a point claim.

spike 10 showed single-shot results flip on sampling noise, so we sample the new
operator N times per model and report the distribution of cross-source metrics,
then compare against spike 10's multisample.json (the SAME corpus + rubric, old
operator) — isolating the operator change.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from rerun11 import (make_client, run_combine11, BASELINE_MODEL, ITER_MODEL,
                     corpus as _c, rubric)
score_artifact = rubric.score_artifact
verdict = rubric.verdict

MODELS = {
    "1.5b": BASELINE_MODEL,
    "4b": ITER_MODEL,
}


def sample(model_key: str, n: int, min_cs: int = 2) -> dict:
    client = make_client("json")
    model = MODELS[model_key]
    rows = []
    for i in range(n):
        try:
            out = run_combine11(client, model, _c.QUERY, _c.SOURCES, min_cross_source=min_cs)
        except Exception as e:  # noqa: BLE001
            rows.append({"error": f"{type(e).__name__}: {e}"})
            print(f"  [{model_key} {i+1}/{n}] ERROR", file=sys.stderr)
            continue
        if "error" in out:
            rows.append({"error": out["error"]})
            print(f"  [{model_key} {i+1}/{n}] rejected: {out['error'][:60]}", file=sys.stderr)
            continue
        s = out["scores"]
        v = out["verdict"]
        rows.append({"scores": s, "pass": v["all_pass"],
                     "completion_fired": out["report"]["completion_fired"],
                     "n_cross_final": out["report"]["n_cross_source_final"]})
        print(f"  [{model_key} {i+1}/{n}] n={s['n_claims']} ncross={s['n_cross_source']} "
              f"rate={s['cross_source_rate']} v={s['verbatim_rate']} "
              f"completion={out['report']['completion_fired']} pass={v['all_pass']}",
              file=sys.stderr)

    ok = [r for r in rows if "scores" in r]
    def _col(name):
        return [r["scores"][name] for r in ok if r["scores"].get(name) is not None]

    summary = {"model": model_key, "n_requested": n, "n_ok": len(ok),
               "errors": [r.get("error") for r in rows if "error" in r],
               "pass_count": sum(1 for r in ok if r["pass"]),
               "completion_fired_count": sum(1 for r in ok if r["completion_fired"]),
               "n_cross_final_values": [r["n_cross_final"] for r in ok]}
    for name in ("verbatim_rate", "overlap", "cross_source_rate", "n_claims",
                 "n_cross_source", "citation_hit"):
        vals = _col(name)
        if vals:
            summary[name] = {"values": vals,
                             "median": round(statistics.median(vals), 3),
                             "min": round(min(vals), 3), "max": round(max(vals), 3)}
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="1.5b,4b")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--out", default="multisample11.json")
    args = ap.parse_args()

    out = {}
    for key in args.models.split(","):
        print(f"--- sampling {key} x{args.n} (new operator) ---", file=sys.stderr)
        out[key] = sample(key, args.n)

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    print(f"\n{'model':8} {'pass':6} {'ncross(med/min/max)':22} {'cross_rate':22} {'v(med)':10}")
    for k, v in out.items():
        nc = v.get("n_cross_source", {})
        cr = v.get("cross_source_rate", {})
        vb = v.get("verbatim_rate", {})
        print(f"{k:8} {v['pass_count']}/{v['n_ok']:<4} "
              f"{str((nc.get('median'), nc.get('min'), nc.get('max'))):22} "
              f"{str((cr.get('median'), cr.get('min'), cr.get('max'))):22} "
              f"{str(vb.get('median')):10}")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
