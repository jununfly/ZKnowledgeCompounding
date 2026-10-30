"""Controlled single-call probe for qwen3.5:9b-mlx.

One clean judge call with a long timeout (600s) so we capture latency + JSON
compliance + the actual verdict WITHOUT the 300s timeout/retry noise.
"""
import os
import sys
import time
from pathlib import Path

# Local Ollama must bypass the WorkBuddy proxy.
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "spike-12-hallucination-judge"))
import judge  # noqa: E402
from openai import OpenAI  # noqa: E402

MODEL = "qwen3.5:9b-mlx"
OLLAMA_BASE = "http://localhost:11434/v1"
EXTRA_BODY = {"think": False, "options": {"num_ctx": 8192}}

client = OpenAI(base_url=OLLAMA_BASE, api_key="ollama", timeout=600)


def judge_one(ex, temperature=0.2):
    t = time.time()
    j = judge.judge_claim(
        lambda p, s: parse_call(p, s, temperature), ex["claim"], judge.corpus.SOURCES
    )
    return j, round(time.time() - t, 1)


def parse_call(prompt, system, temperature):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        temperature=temperature, stream=False, timeout=600,
        extra_body=EXTRA_BODY,
    )
    content = resp.choices[0].message.content or ""
    Path("probe_9b_raw.txt").write_text(content, encoding="utf-8")
    print(f"[raw length={len(content)}] head:\n{content[:1500]}", file=sys.stderr)
    try:
        return judge.parse_judgment(content)
    except Exception as e:  # noqa: BLE001
        print(f"[parse_judgment FAILED: {type(e).__name__}: {e}]", file=sys.stderr)
        # return a fallback so judge_claim can still continue
        return judge.Judgment(atomic_facts=[], overall="unsupported",
                              reason=f"parse-error:{type(e).__name__}")


# pick the first contradicted example (tests the key capability: catch contradiction)
ex = next(e for e in judge.GOLDEN if e["truth"] == "contradicted")
print(f"example id={ex['id']} truth={ex['truth']}", file=sys.stderr)
j, dt = judge_one(ex)
print(f"latency={dt}s", file=sys.stderr)
print(f"overall={j.overall} atomic_facts={len(j.atomic_facts)}", file=sys.stderr)
for af in j.atomic_facts:
    print(f"  - [{af.verdict}] {af.fact}  (ev: {af.evidence})", file=sys.stderr)
print(f"reason={j.reason}", file=sys.stderr)
print("__LATENCY_S__", dt, "__OVERALL__", j.overall, "__N_ATOMIC__", len(j.atomic_facts))
