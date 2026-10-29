"""Spike 02 runner: calibrate, evaluate, and show per-item detail."""
from samples import ROUTES, EVAL_SET, CALIB_SET
from router import TfidfEncoder, DualTrackRouter, evaluate, _info_tokens


def build():
    enc = TfidfEncoder()
    r = DualTrackRouter(enc)
    for name, utts in ROUTES.items():
        r.add_route(name, utts)
    r.build()
    return r


def main():
    r = build()
    t = r.calibrate([x for x, _ in CALIB_SET], [y for _, y in CALIB_SET])
    print(f"calibrated threshold = {t:.2f}  (target misroute on CALIB = 5%)")

    cm = evaluate(r, CALIB_SET)
    print(f"  on CALIB  : abstain={cm['abstain_rate']:.1%} "
          f"misroute={cm['misroute_rate']:.1%} coverage={cm['coverage']:.1%}")

    m = evaluate(r, EVAL_SET)
    print(f"  on EVAL   : abstain={m['abstain_rate']:.1%} "
          f"misroute={m['misroute_rate']:.1%} coverage={m['coverage']:.1%} "
          f"acc_on_routed={m['accuracy_on_routed']:.1%}")
    print(f"  ambiguous : {m['abstain_on_ambiguous']}/{m['ambiguous_total']} abstained, "
          f"false_commit={m['false_commit']}")

    print("\nper-item (EVAL):")
    print(f"{'true':<8} {'pred':<8} {'score':>6}  text")
    print("-" * 78)
    for text, true in EVAL_SET:
        pred, score = r.predict(text)
        flag = ""
        if pred is None and true is not None:
            flag = "  <- missed (abstained but had a true label)"
        elif pred is not None and true is None:
            flag = "  <- FALSE COMMIT (ambiguous but routed)"
        elif pred != true:
            flag = "  <- MISROUTE"
        print(f"{str(true):<8} {str(pred):<8} {score:>6.3f}  {text[:38]}{flag}")

    # Threshold sweep to show the trade-off explicitly
    print("\nthreshold sweep on EVAL:")
    print(f"{'t':>5} {'abstain':>8} {'misroute':>9} {'coverage':>9}")
    for tt in [i / 20 for i in range(0, 21)]:
        r.threshold = tt
        s = evaluate(r, EVAL_SET)
        print(f"{tt:>5.2f} {s['abstain_rate']:>8.1%} {s['misroute_rate']:>9.1%} {s['coverage']:>9.1%}")


    # IMPORTANT: the sweep below mutates r.threshold, so restore the calibrated
    # value first — otherwise later probes silently run at the wrong threshold.
    r.threshold = t

    # Adversarial probe: LONG but genuinely ambiguous items.
    # The eval set's ambiguous items are all short, which flatters the
    # information-content gate. This probe exposes that boundary condition.
    adversarial = [
        "这个事情我现在还没完全想清楚，可能要等到下周再看看具体情况再决定",
        "关于那个方案我目前还在犹豫，需要和团队再讨论一下才能定下来",
        "这份材料我先放一放，等手头的事情忙完了之后再回头处理",
    ]
    print("\n\nADVERSARIAL PROBE — long but ambiguous (true label = None):")
    print(f"{'ntok':>5} {'score':>6} {'pred':<9} outcome   text")
    print("-" * 78)
    bad = 0
    for t in adversarial:
        pred, score = r.predict(t)
        ok = pred is None
        bad += 0 if ok else 1
        print(f"{_info_tokens(t):>5} {score:>6.3f} {str(pred):<9} "
              f"{'OK' if ok else 'FALSE COMMIT'}       {t[:28]}")
    print(f"\nfalse commits on long-ambiguous: {bad}/{len(adversarial)}")
    print("  -> the length/information gate only catches SHORT vagueness.")
    print("  -> long ambiguity needs a real signal (dedicated ambiguity route")
    print("     or a decision model), not threshold tuning.")


if __name__ == "__main__":
    main()
