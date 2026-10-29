"""Spike 02 — real-encoder verification via Ollama (local, no HuggingFace).

Ollama is ZKC's MVP inference layer, so this also exercises the encoder path the
product will actually ship. It avoids HuggingFace, which is blocked/unreliable in
this environment (see run_spike_real.py + README for the BGE attempt that failed
with SSL EOF / timeouts).

Reuses the ZKC-owned routing logic from router.py (DualTrackRouter, calibrate,
evaluate, _info_tokens) and the labelled data in samples.py. Only the encoder
differs: an Ollama-backed dense embedder, L2-normalised so cosine is in [-1, 1]
and comparable to the TF-IDF path.
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request

from samples import ROUTES, EVAL_SET, CALIB_SET
from router import TfidfEncoder, DualTrackRouter, evaluate, _info_tokens

ADVERSARIAL = [
    "这个事情我现在还没完全想清楚，可能要等到下周再看看具体情况再决定",
    "关于那个方案我目前还在犹豫，需要和团队再讨论一下才能定下来",
    "这份材料我先放一放，等手头的事情忙完了之后再回头处理",
]


class OllamaAdapter:
    """Dense embedder backed by Ollama's /api/embed endpoint (local)."""

    def __init__(self, model: str, url: str = "http://localhost:11434"):
        self.model = model
        self.url = url

    def fit(self, corpus):
        return self  # pre-trained; nothing to fit

    def encode(self, texts):
        payload = json.dumps({"model": self.model, "input": list(texts)}).encode()
        req = urllib.request.Request(
            self.url + "/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
        out = []
        for vec in data["embeddings"]:
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append({str(i): float(v) / norm for i, v in enumerate(vec)})
        return out


def build(encoder):
    r = DualTrackRouter(encoder)
    for name, utts in ROUTES.items():
        r.add_route(name, utts)
    r.build()
    return r


def report(tag, r):
    m = evaluate(r, EVAL_SET)
    bad = sum(1 for t in ADVERSARIAL if r.predict(t)[0] is not None)
    print(f"\n[{tag}]")
    print(f"  threshold={r.threshold:.2f} min_tokens={r.min_tokens}")
    print(f"  EVAL : abstain={m['abstain_rate']:.1%} misroute={m['misroute_rate']:.1%} "
          f"coverage={m['coverage']:.1%} acc_on_routed={m['accuracy_on_routed']:.1%}")
    print(f"  ambiguous abstained: {m['abstain_on_ambiguous']}/{m['ambiguous_total']}")
    print(f"  long-ambiguous false commits: {bad}/{len(ADVERSARIAL)}")
    return m, bad


def separation(tag, r):
    import statistics
    rows = [(true, r.score(text)[1], _info_tokens(text)) for text, true in EVAL_SET]
    amb = [x for x in rows if x[0] is None]
    clr = [x for x in rows if x[0] is not None]
    amb_scores = [a[1] for a in amb]
    clr_scores = [c[1] for c in clr]
    sep = max(amb_scores) < min(clr_scores)
    print(f"\n--- separation with {tag} ---")
    print(f"  score: ambiguous mean={statistics.mean(amb_scores):.3f} "
          f"clear mean={statistics.mean(clr_scores):.3f}")
    print(f"  score: ambiguous max={max(amb_scores):.3f} clear min={min(clr_scores):.3f}  "
          f"{'SEPARATED' if sep else 'OVERLAP'}")
    return sep


def main():
    models = sys.argv[1:] or ["nomic-embed-text", "qwen3-embedding"]

    # --- baseline: lexical encoder (no deps) ---
    tf = build(TfidfEncoder())
    tf.calibrate([x for x, _ in CALIB_SET], [y for _, y in CALIB_SET])
    report("TF-IDF (lexical)", tf)

    # --- real encoders via Ollama ---
    for model in models:
        print(f"\nloading Ollama model: {model} ...")
        r = build(OllamaAdapter(model))
        r.calibrate([x for x, _ in CALIB_SET], [y for _, y in CALIB_SET])
        report(f"Ollama ({model})", r)
        separation(f"Ollama ({model})", r)


if __name__ == "__main__":
    main()
