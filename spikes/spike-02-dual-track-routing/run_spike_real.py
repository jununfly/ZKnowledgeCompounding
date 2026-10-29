"""Spike 02 — re-run with the REAL encoder (semantic-router + local FastEmbed).

The ZKC logic (routes, calibration, dual-signal abstention, evaluation) is
unchanged; only the encoder differs. This removes the main caveat of the
TF-IDF run, which used a lexical encoder.
"""
from __future__ import annotations

import sys

from samples import ROUTES, EVAL_SET, CALIB_SET
from router import TfidfEncoder, DualTrackRouter, evaluate, _info_tokens


class FastEmbedAdapter:
    """Adapt semantic-router's FastEmbedEncoder to the encoder interface."""

    def __init__(self, model: str):
        from semantic_router.encoders import FastEmbedEncoder
        self.model = model
        self.enc = FastEmbedEncoder(name=model)

    def fit(self, corpus):
        return self  # pre-trained; nothing to fit

    def encode(self, texts):
        out = self.enc(list(texts))
        return [{str(i): float(v) for i, v in enumerate(vec)} for vec in out]


def build(encoder):
    r = DualTrackRouter(encoder)
    for name, utts in ROUTES.items():
        r.add_route(name, utts)
    r.build()
    return r


def report(tag, r, calib_threshold):
    m = evaluate(r, EVAL_SET)
    adv = [
        "这个事情我现在还没完全想清楚，可能要等到下周再看看具体情况再决定",
        "关于那个方案我目前还在犹豫，需要和团队再讨论一下才能定下来",
        "这份材料我先放一放，等手头的事情忙完了之后再回头处理",
    ]
    bad = sum(1 for t in adv if r.predict(t)[0] is not None)
    print(f"\n[{tag}]")
    print(f"  threshold={r.threshold:.2f} min_tokens={r.min_tokens}")
    print(f"  EVAL : abstain={m['abstain_rate']:.1%} misroute={m['misroute_rate']:.1%} "
          f"coverage={m['coverage']:.1%} acc_on_routed={m['accuracy_on_routed']:.1%}")
    print(f"  ambiguous abstained: {m['abstain_on_ambiguous']}/{m['ambiguous_total']}")
    print(f"  long-ambiguous false commits: {bad}/{len(adv)}")
    return m, bad


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "BAAI/bge-small-zh-v1.5"

    # --- baseline: lexical encoder ---
    tf = build(TfidfEncoder())
    tf.calibrate([x for x, _ in CALIB_SET], [y for _, y in CALIB_SET])
    report("TF-IDF (lexical)", tf, tf.threshold)

    # --- real encoder ---
    print(f"\nloading FastEmbed model: {model} ...")
    r = build(FastEmbedAdapter(model))
    r.calibrate([x for x, _ in CALIB_SET], [y for _, y in CALIB_SET])
    report(f"FastEmbed ({model})", r, r.threshold)

    print("\n--- separation with the REAL encoder ---")
    rows = []
    for text, true in EVAL_SET:
        name, score = r.score(text)
        rows.append((true, score, _info_tokens(text)))
    import statistics
    amb = [x for x in rows if x[0] is None]
    clr = [x for x in rows if x[0] is not None]
    print(f"  score  : ambiguous mean={statistics.mean([a[1] for a in amb]):.3f} "
          f"clear mean={statistics.mean([c[1] for c in clr]):.3f}")
    print(f"  score  : ambiguous max={max(a[1] for a in amb):.3f} "
          f"clear min={min(c[1] for c in clr):.3f}  "
          f"{'SEPARATED' if max(a[1] for a in amb) < min(c[1] for c in clr) else 'OVERLAP'}")


if __name__ == "__main__":
    main()
