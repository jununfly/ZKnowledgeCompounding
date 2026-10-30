"""Spike 10 runner: three-arm re-test, rubric-scored, writes a JSON report."""
import argparse
import json
import sys
from pathlib import Path

import corpus
from rerun import ARMS, run_all, TARGET_MODEL

OUT = Path(__file__).resolve().parent / "report.json"


def _fmt(label, r):
    d, c = r.get("distill", {}), r.get("combine", {})
    print(f"\n=== {label} ===")
    print(f"  model={r['model']}  policy={r['policy']}")
    if "error" in d:
        print(f"  distill ERROR: {d['error']}")
    else:
        s = d["scores"]
        print(f"  distill  verbatim={s['verbatim_rate']} abstraction={s['abstraction']} "
              f"struct={s['structural_fit']}  attempts={d['retry'].get('n_attempts')} "
              f"growth={d['retry'].get('prompt_growth')}")
        print(f"           pass={d['verdict']['all_pass']} {d['verdict']['checks']}")
        print(f"           statement={d['draft'].get('statement','')[:70]}")
    if "error" in c:
        print(f"  combine ERROR: {c['error']}")
    else:
        s = c["scores"]
        print(f"  combine  verbatim={s['verbatim_rate']} cross_source={s['cross_source_rate']} "
              f"overlap={s['overlap']} citation_hit={s.get('citation_hit')} "
              f"struct={s['structural_fit']} n_claims={s['n_claims']}")
        print(f"           pass={c['verdict']['all_pass']} {c['verdict']['checks']}")
        print(f"           struct_detail={s['structural_detail']}")
        for cl in c["artifact"].get("claims", [])[:3]:
            print(f"           - {cl.get('statement','')[:60]}  <- {cl.get('evidence_ids')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="A,B,C", help="which arms to run, e.g. A,C")
    ap.add_argument("--mode", default="json", choices=["json", "tools"])
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    wanted = [a for a in ARMS if a[0][0] in args.arms.split(",")]
    if not wanted:
        print("no arms selected", file=sys.stderr)
        return 1

    print(f"corpus: {len(corpus.SOURCES)} sources | mode={args.mode} | arms={[w[0] for w in wanted]}")
    distill_sources = [s for s in corpus.SOURCES if s["id"] in corpus.DISTILL_SOURCE_IDS]
    results = run_all(corpus.SOURCES, corpus.QUERY, distill_sources,
                      mode=args.mode, arms=wanted)

    for label, r in results.items():
        _fmt(label, r)

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    print(f"\nreport -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
