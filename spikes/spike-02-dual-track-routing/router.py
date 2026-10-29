"""Spike 02: calibrated dual-track routing with abstention.

The ZKC-owned part under test is NOT the embedding model — it is:
  1. two-track route definitions (static / dynamic),
  2. threshold calibration that turns a raw similarity into an act/don't-act decision,
  3. an explicit ABSTAIN path (return None) instead of forcing a choice.

The encoder is pluggable so the same logic can run on a local TF-IDF encoder
(no dependencies) or on semantic-router + FastEmbed when available.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# An item is routed only when its best score clears the calibrated threshold.
# Calibration learns this threshold from labelled data.
DEFAULT_TARGET_MISROUTE = 0.05


def _tokens(text: str) -> list[str]:
    """Chinese-friendly tokenisation: latin words + character unigrams and bigrams."""
    text = text.lower()
    latin = re.findall(r"[a-z0-9]+", text)
    han = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = [han[i] + han[i + 1] for i in range(len(han) - 1)]
    return latin + han + bigrams


class TfidfEncoder:
    """Dependency-free encoder: sub-linear TF * smoothed IDF, L2-normalised."""

    def __init__(self) -> None:
        self.idf: dict[str, float] = {}
        self.fitted = False

    def fit(self, corpus: list[str]) -> "TfidfEncoder":
        docs = [_tokens(d) for d in corpus]
        n = len(docs)
        df: Counter[str] = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self.fitted = True
        return self

    def encode(self, texts: list[str]) -> list[dict[str, float]]:
        if not self.fitted:
            self.fit(texts)
        out = []
        for t in texts:
            tf = Counter(_tokens(t))
            vec = {tok: (1.0 + math.log(c)) * self.idf.get(tok, 0.0) for tok, c in tf.items()}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            out.append({k: v / norm for k, v in vec.items()})
        return out


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def _info_tokens(text: str) -> int:
    """Distinct-token count: a proxy for how much information an item carries."""
    return len(set(_tokens(text)))


class DualTrackRouter:
    def __init__(self, encoder) -> None:
        self.encoder = encoder
        self.routes: dict[str, list[dict[str, float]]] = {}
        self.threshold = 0.0
        self.min_tokens = 0   # information-content gate for abstention

    def add_route(self, name: str, utterances: list[str]) -> None:
        self.routes.setdefault(name, [])
        self.routes[name].extend(utterances)

    def build(self) -> None:
        corpus = [u for utts in self.routes.values() for u in utts]
        self.encoder.fit(corpus)
        self.route_vecs = {
            name: self.encoder.encode(utts) for name, utts in self.routes.items()
        }

    def score(self, text: str) -> tuple[str | None, float]:
        vec = self.encoder.encode([text])[0]
        best_name, best = None, -1.0
        for name, vecs in self.route_vecs.items():
            for rv in vecs:
                s = cosine(vec, rv)
                if s > best:
                    best, best_name = s, name
        return best_name, max(0.0, best)

    def predict(self, text: str) -> tuple[str | None, float]:
        # Two independent abstention signals:
        #  1. not similar enough to any route
        #  2. not enough information to make a judgement at all
        if _info_tokens(text) < self.min_tokens:
            return None, self.score(text)[1]
        name, score = self.score(text)
        if score < self.threshold:
            return None, score
        return name, score

    def calibrate(self, texts: list[str], labels: list[str | None],
                  target_misroute: float = DEFAULT_TARGET_MISROUTE) -> float:
        """Pick the lowest threshold that keeps misroutes under target, maximising coverage."""
        scored = []
        for t, y in zip(texts, labels):
            name, score = self.score(t)
            wrong = (y is None) or (name != y)
            scored.append((score, _info_tokens(t), wrong))

        best_t, best_mt, best_key = 1.0, 0, None
        grid = [i / 100 for i in range(0, 101)]
        tok_candidates = sorted({0} | {nt for _, nt, _ in scored})
        for mt in tok_candidates:
            live = [(s, w) for s, nt, w in scored if nt >= mt]
            if not live:
                continue
            for t in grid:
                routed = [s for s, _ in live if s >= t]
                mis = [s for s, w in live if s >= t and w]
                misroute = len(mis) / len(routed) if routed else 0.0
                coverage = len(routed) / len(scored)
                if misroute <= target_misroute:
                    key = (coverage, -t, -mt)
                    if best_key is None or key > best_key:
                        best_key, best_t, best_mt = key, t, mt
        if best_key is None:
            best_mis = None
            for mt in tok_candidates:
                live = [(s, w) for s, nt, w in scored if nt >= mt]
                if not live:
                    continue
                for t in grid:
                    routed = [s for s, _ in live if s >= t]
                    mis = [s for s, w in live if s >= t and w]
                    misroute = len(mis) / len(routed) if routed else 0.0
                    coverage = len(routed) / len(scored)
                    key = (misroute, -coverage)
                    if best_mis is None or key < best_mis:
                        best_mis, best_t, best_mt = key, t, mt
        self.threshold = best_t
        self.min_tokens = best_mt
        return best_t


def evaluate(router: DualTrackRouter, samples: list[tuple[str, str | None]]) -> dict:
    total = len(samples)
    abstained = misroute = correct = 0
    abstain_on_ambiguous = false_commit = 0
    amb_total = 0
    for text, true in samples:
        pred, _ = router.predict(text)
        if true is None:
            amb_total += 1
        if pred is None:
            abstained += 1
            if true is None:
                abstain_on_ambiguous += 1
        elif pred == true:
            correct += 1
        else:
            misroute += 1
            if true is None:
                false_commit += 1
    routed = total - abstained
    return {
        "total": total,
        "threshold": round(router.threshold, 2),
        "abstained": abstained,
        "routed": routed,
        "correct": correct,
        "misroute": misroute,
        "abstain_rate": abstained / total if total else 0.0,
        "misroute_rate": misroute / routed if routed else 0.0,
        "accuracy_on_routed": correct / routed if routed else 0.0,
        "coverage": routed / total if total else 0.0,
        "ambiguous_total": amb_total,
        "abstain_on_ambiguous": abstain_on_ambiguous,
        "false_commit": false_commit,
    }
