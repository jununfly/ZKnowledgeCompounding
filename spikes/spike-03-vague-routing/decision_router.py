"""Spike 03 — Approach B: DecisionRouter (LLM-as-judge, local Ollama).

Instead of embedding similarity + threshold, a single local LLM call decides the
track directly, returning structured JSON: track + confidence + reason. This uses
actual semantic reasoning, which Spike 02's similarity overlap could not separate.

ZKC-owned decision semantics are encoded in the SYSTEM_PROMPT (the ZKC track
definitions). The model is just the reasoning engine — swappable (Ollama is the MVP
inference layer, matching ZKC's Ollama + Instructor + LangGraph stack).

A confidence gate (conf < GATE => vague) is the lightweight safety valve; the LLM's
own "vague" class already absorbs uncertainty.
"""
from __future__ import annotations

import json
import re
import urllib.request

SYSTEM_PROMPT = (
    "你是 ZKC 双轨分类器。只输出 JSON："
    '{"track":"static|dynamic|vague","confidence":0到1,"reason":"一句话"}。'
    "track 定义："
    "static=客观事实/时间线/长生命周期（此刻可信、未来可更新）；"
    "dynamic=当下行动/短生命周期/易腐化（此刻有用、快速衰减）；"
    "vague=不确定/含糊/需再确认/未想清楚。"
    "若信息不足以判断或表述含糊，track 必须为 vague。不要猜测。"
)

GATE = 0.5  # confidence below this => force vague


class DecisionRouter:
    def __init__(self, model: str = "qwen2.5-coder:1.5b", url: str = "http://localhost:11434"):
        self.model = model
        self.url = url

    def _chat(self, text: str) -> dict:
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        }).encode()
        req = urllib.request.Request(
            self.url + "/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        content = data.get("message", {}).get("content", "")
        # Defensive parse: extract first {...} block
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return {"track": "vague", "confidence": 0.0, "reason": "parse-fail"}
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"track": "vague", "confidence": 0.0, "reason": "json-fail"}
        return obj

    def predict(self, text: str) -> tuple[str | None, float]:
        obj = self._chat(text)
        track = obj.get("track")
        try:
            conf = float(obj.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        if track not in ("static", "dynamic", "vague"):
            track = "vague"
        if conf < GATE:
            track = "vague"
        return track, conf
