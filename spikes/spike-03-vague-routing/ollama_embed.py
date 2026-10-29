"""Local Ollama dense embedder (reused from Spike 02's run_spike_ollama.py).

Kept self-contained so Spike 03 has no cross-dir runtime import at call time; it
mirrors the adapter there. L2-normalised so cosine lives in [-1, 1].
"""
from __future__ import annotations

import json
import math
import urllib.request


class OllamaEmbed:
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
