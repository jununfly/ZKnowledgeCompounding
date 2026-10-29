"""Spike 03 — Approach A: explicit 3-way routing (static / dynamic / vague).

Builds on Spike 02's DualTrackRouter (the ZKC-owned calibration + abstain logic),
but adds a third *vague* route so ambiguity has a home instead of being forced into
a track or silently dropped. The information-content (min_tokens) gate from Spike 02
is dropped: in the 3-way design, low-information items like "嗯" are *vague*, not
"unknown", and the vague route captures them by similarity.

Success criteria this router must satisfy (the Spike 02 failure modes):
  - F1: short ambiguous items route to "vague" (not falsely committed to a track)
  - F2: long-vague adversarial sentences route to "vague" (NOT to "dynamic")
  - keep: clear static/dynamic items routed to their own track
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spike-02-dual-track-routing"))
from router import DualTrackRouter  # noqa: E402


class ThreeWayRouter(DualTrackRouter):
    """static/dynamic/vague router. Drops the info gate; relies on the vague route."""

    def predict(self, text: str) -> tuple[str | None, float]:
        # No min_tokens gate: vague route is the sink for low-information / uncertain.
        name, score = self.score(text)
        if score < self.threshold:
            return None, score
        return name, score

    def calibrate(self, texts, labels, target_dangerous: float = 0.05) -> float:
        """Pick the lowest threshold keeping DANGEROUS routings under target.

        DANGEROUS = a clear item committed to the wrong track, OR an ambiguous
        (vague) item committed to a real track. Routing a clear item to "vague" is
        safe under-coverage (not dangerous); routing ambiguous to "vague" is correct.
        """
        scored = []
        for t, y in zip(texts, labels):
            name, score = self.score(t)
            dangerous = (name != y) and not (y == "vague" and name == "vague")
            # y==vague & name in track  -> dangerous (false commit)
            # y==track & name==vague    -> safe under-cover (not dangerous)
            # y==track & name==other    -> dangerous (track confusion)
            scored.append((score, name, y, dangerous))

        best_t, best_key = 1.0, None
        grid = [i / 100 for i in range(0, 101)]
        for t in grid:
            routed = [(s, n, y, d) for s, n, y, d in scored if s >= t]
            if not routed:
                continue
            dangerous = [x for x in routed if x[3]]
            dangerous_rate = len(dangerous) / len(routed)
            coverage = len(routed) / len(scored)
            if dangerous_rate <= target_dangerous:
                key = (coverage, -t)
                if best_key is None or key > best_key:
                    best_key, best_t = key, t
        self.threshold = best_t
        return best_t


def evaluate_3way(router: ThreeWayRouter, samples) -> dict:
    """samples: list of (text, label) with label in {static, dynamic, vague}."""
    total = len(samples)
    correct = false_commit = track_confusion = safe_undercover = abstained = 0
    adv_total = adv_vague = adv_dynamic = 0
    for text, true in samples:
        pred, _ = router.predict(text)
        if pred is None:
            abstained += 1
            continue
        if pred == true:
            correct += 1
        elif true == "vague" and pred in ("static", "dynamic"):
            false_commit += 1
        elif true in ("static", "dynamic") and pred == "vague":
            safe_undercover += 1
        else:  # true track, pred = other track
            track_confusion += 1
    routed = total - abstained
    return {
        "total": total,
        "threshold": round(getattr(router, "threshold", float("nan")), 2),
        "abstained": abstained,
        "routed": routed,
        "correct": correct,
        "coverage": routed / total if total else 0.0,
        "accuracy_on_routed": correct / routed if routed else 0.0,
        "false_commit_on_vague": false_commit,      # DANGEROUS: vague pushed to a track
        "track_confusion": track_confusion,          # DANGEROUS: static<->dynamic swap
        "dangerous_total": false_commit + track_confusion,
        "safe_undercover": safe_undercover,          # clear item → vague (safe)
    }
