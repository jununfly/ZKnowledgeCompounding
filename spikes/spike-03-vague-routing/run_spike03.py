"""Spike 03 — full comparison runner.

Verifies the two candidate fixes for Spike 02's failure modes:
  A) explicit 3-way routing (static / dynamic / vague)  — embedding + threshold
  B) DecisionRouter (LLM-as-judge, local Ollama)         — single LLM call

Measures on the shared EVAL_SET (24 clear + 8 short-ambiguous) + 3 long-vague
adversarial probes:
  - F2: adversarial NOT committed to dynamic (the critical fix)
  - F1: no ambiguous item committed to a track (false_commit_on_vague == 0)
  - clear accuracy / coverage / dangerous total

Usage:  python3 run_spike03.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spike-02-dual-track-routing"))
from router import TfidfEncoder  # noqa: E402

from samples_v3 import ROUTES, ROUTES_3WAY, CALIB_SET, CALIB_SET_3WAY, eval_3way, ADVERSARIAL  # noqa: E402
from router3 import ThreeWayRouter, evaluate_3way  # noqa: E402
from ollama_embed import OllamaEmbed  # noqa: E402
from decision_router import DecisionRouter  # noqa: E402


def build_3way(encoder):
    r = ThreeWayRouter(encoder)
    for n, u in ROUTES_3WAY.items():
        r.add_route(n, u)
    r.build()
    r.calibrate([x for x, _ in CALIB_SET_3WAY], [y for _, y in CALIB_SET_3WAY])
    return r


def line(tag, m, adv_vague, adv_dynamic):
    print(f"  [{tag}]")
    print(f"    threshold={m['threshold']:.2f} coverage={m['coverage']:.1%} "
          f"acc_on_routed={m['accuracy_on_routed']:.1%}")
    print(f"    dangerous_total={m['dangerous_total']} "
          f"(false_commit_on_vague={m['false_commit_on_vague']}, "
          f"track_confusion={m['track_confusion']}) safe_undercover={m['safe_undercover']}")
    print(f"    ADVERSARIAL: vague={adv_vague}/3  dynamic={adv_dynamic}/3  "
          f"-> F2 {'PASS' if adv_dynamic == 0 else 'FAIL'}")


def main():
    ev = eval_3way()

    print("=" * 70)
    print("APPROACH A — explicit 3-way routing")
    print("=" * 70)

    # lexical baseline
    r = build_3way(TfidfEncoder())
    m = evaluate_3way(r, ev)
    adv = [r.predict(t)[0] for t in ADVERSARIAL]
    line("TF-IDF (lexical)", m, adv.count("vague"), adv.count("dynamic"))

    for model in ("nomic-embed-text", "qwen3-embedding"):
        try:
            r = build_3way(OllamaEmbed(model))
        except Exception as e:
            print(f"  [Ollama {model}] SKIP: {e}")
            continue
        m = evaluate_3way(r, ev)
        adv = [r.predict(t)[0] for t in ADVERSARIAL]
        line(f"Ollama ({model})", m, adv.count("vague"), adv.count("dynamic"))

    print()
    print("=" * 70)
    print("APPROACH B — DecisionRouter (LLM-as-judge, qwen2.5-coder:1.5b)")
    print("=" * 70)
    try:
        dr = DecisionRouter()
        dr._chat("ping")
    except Exception as e:
        print(f"  DecisionRouter SKIP: {e}")
        return
    m = evaluate_3way(dr, ev)
    adv = [dr.predict(t)[0] for t in ADVERSARIAL]
    line("DecisionRouter", m, adv.count("vague"), adv.count("dynamic"))


if __name__ == "__main__":
    main()
