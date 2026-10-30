"""Spike 12 real-model evaluation: can qwen3.5:4b-mlx serve as the faithfulness gate?

Wires Ollama + a raw OpenAI client (NOT instructor — instructor.Mode.JSON hangs on
qwen3.5's reasoning stream via Ollama) + spike 10's FROZEN resilient-style retry.
Parses the model output defensively with judge.parse_judgment. Runs the judge over
the golden set, multiple samples per example (spike 10 showed single-shot flips on
noise), and reports the confusion matrix + the dangerous-false-negative rate — the
only metric that decides whether 4B can be an automated gate or we need
human-in-the-loop / a larger judge model.

NOTE (measured on this 16 GB box, see README §5): qwen3.5:4b-mlx takes ~110-130 s
PER judge call and emits Markdown prose rather than JSON, so the automated eval does
not complete here. The script is correct and will run on a faster / JSON-compliant
judge model — just point MODEL at it and rerun.

Usage:
  python run_spike12.py --samples 3 --out multisample12.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import sys
import time
from pathlib import Path

from openai import OpenAI

import judge
from judge import Judgment, evaluate, parse_judgment

_HERE = Path(__file__).resolve().parent
_SPIKES = _HERE.parent

# Local Ollama must bypass the WorkBuddy proxy (HTTP_PROXY is set in this env and
# httpx would otherwise route localhost:11434 through it and hang). Set before the
# client is constructed.
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # register BEFORE exec: @dataclass needs sys.modules[__name__]
    spec.loader.exec_module(mod)
    return mod


llm_client = _load("s12_llm_client", _SPIKES / "spike-10-model-quality" / "llm_client.py")
condense_error = llm_client.condense_error  # reuse the bounded hint

OLLAMA_BASE = "http://localhost:11434/v1"
MODEL = "qwen3.5:4b-mlx"
NUM_CTX = 8192
EXTRA_BODY = {"think": False, "options": {"num_ctx": NUM_CTX}}


def make_client():
    return OpenAI(base_url=OLLAMA_BASE, api_key="ollama", timeout=300)


def make_llm_fn(client, temperature: float = 0.2, max_attempts: int = 2, model: str = MODEL):
    """Raw completion + defensive JSON parse (instructor JSON-mode hangs here)."""
    def fn(prompt: str, system: str) -> Judgment:
        last_err: Exception | None = None
        for attempt in range(max_attempts):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": prompt}],
                    temperature=temperature, stream=False, timeout=300,
                    extra_body=EXTRA_BODY,
                )
                content = resp.choices[0].message.content or ""
                return parse_judgment(content)
            except Exception as e:  # noqa: BLE001 - retry on any validation/API failure
                last_err = e
        # all attempts failed to parse -> emit a fallback judgment (judge_claim will
        # then trust this overall, or retry once more inside judge_claim).
        return Judgment(atomic_facts=[], overall="unsupported",
                        reason=f"parse-error:{condense_error(last_err) if last_err else 'none'}")
    return fn


def _timed_judge(fn, ex):
    t = time.time()
    j = judge.judge_claim(fn, ex["claim"], judge.corpus.SOURCES)
    return j, round(time.time() - t, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--model", default=MODEL, help="judge model tag in Ollama")
    ap.add_argument("--limit", type=int, default=None, help="cap number of golden examples")
    ap.add_argument("--out", default="multisample12.json")
    args = ap.parse_args()

    client = make_client()
    fn = make_llm_fn(client, args.temperature, args.max_attempts, args.model)
    samples = []
    for i in range(args.samples):
        print(f"--- sample {i + 1}/{args.samples} ---", file=sys.stderr)
        # evaluate manually so we get per-example timing
        rows = []
        call_times = []
        for ex in (judge.GOLDEN[:args.limit] if args.limit else judge.GOLDEN):
            try:
                j, dt = _timed_judge(fn, ex)
                call_times.append(dt)
            except Exception as e:  # noqa: BLE001
                print(f"  {ex['id']} ERROR {type(e).__name__}: {e}", file=sys.stderr)
                continue
            rows.append({"id": ex["id"], "truth": ex["truth"], "pred": j.overall,
                         "atomic": len(j.atomic_facts), "dt": dt,
                         "reason": j.reason})
            print(f"    {ex['id']} truth={ex['truth']} pred={j.overall} "
                  f"atomic={len(j.atomic_facts)} {dt}s", file=sys.stderr)

        classes = ["supported", "partial", "unsupported", "contradicted"]
        confusion = {t: {p: 0 for p in classes} for t in classes}
        for r in rows:
            confusion[r["truth"]][r["pred"]] += 1
        n = len(rows)
        correct = sum(1 for r in rows if r["truth"] == r["pred"])
        danger = [r for r in rows if r["truth"] in ("unsupported", "contradicted")]
        danger_fn = [r for r in danger if r["pred"] == "supported"]
        hallu = [r for r in rows if r["truth"] != "supported"]
        hallu_caught = [r for r in hallu if r["pred"] != "supported"]
        empty_fallback = sum(1 for r in rows if r["atomic"] == 0)
        rep = {
            "n": n, "accuracy": round(correct / n, 3) if n else None,
            "confusion": confusion,
            "dangerous_false_negative_rate": round(len(danger_fn) / len(danger), 3) if danger else None,
            "hallucination_catch_rate": round(len(hallu_caught) / len(hallu), 3) if hallu else None,
            "empty_atomic_fallback": empty_fallback,
            "call_time_median_s": round(statistics.median(call_times), 1) if call_times else None,
            "rows": rows,
        }
        samples.append(rep)
        print(f"  acc={rep['accuracy']} danger_FN={rep['dangerous_false_negative_rate']} "
              f"catch={rep['hallucination_catch_rate']} empty_fallback={empty_fallback} "
              f"median_call={rep['call_time_median_s']}s", file=sys.stderr)

    ok = [s for s in samples if "accuracy" in s]
    summary = {"model": args.model, "n_requested": args.samples, "n_ok": len(ok), "samples": samples}
    for key in ("accuracy", "dangerous_false_negative_rate", "hallucination_catch_rate",
                "call_time_median_s", "empty_atomic_fallback"):
        vals = [s[key] for s in ok if s.get(key) is not None]
        if vals:
            summary[key] = {"values": vals,
                            "median": round(statistics.median(vals), 3),
                            "min": round(min(vals), 3), "max": round(max(vals), 3)}
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print("\n" + json.dumps({k: summary[k] for k in
                            ("model", "n_ok", "accuracy", "dangerous_false_negative_rate",
                             "hallucination_catch_rate", "call_time_median_s",
                             "empty_atomic_fallback")}, ensure_ascii=False, indent=2))
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
