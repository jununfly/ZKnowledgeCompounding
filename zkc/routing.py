"""ZKC · 双轨分流引擎（P2.2：DecisionRouter 接入 + 双信号弃权 + 人工兜底）。

设计来源（spike 02 / spike 03 已验证，本模块是它们的生产落地）：
- 信号 A：DecisionRouter —— 单次本地 LLM 调用直接判定轨道（推理而非相似度）。
  ZKC 自有双轨语义编码在 SYSTEM_PROMPT；模型只是可替换推理引擎（Ollama 栈）。
- 信号 B：LexicalRouter —— 词法 TF-IDF 三路，**embedding-free**。
  **关键偏差**：spike 03 曾建议「DecisionRouter + 嵌入相似度」作安全阀，但 R16 硬约束
  embedding 严禁用于安全判定（spike 03 实测 nomic dangerous=3），故第二信号改为词法
  TF-IDF（spike 03 实测 TF-IDF 三路 dangerous=0，安全属性达标）。

双信号弃权规则（见 roadmap 1-3-2 决策）：
- 同时满足 ①LLM conf≥GATE ②词法 conf≥GATE ③两信号轨道一致 才提交真实轨道；
- 任一不满足（含任一信号判 vague / 两信号不一致）→ vague → 人工兜底（安全欠覆盖，非危险）。

离线/本地优先（不变量 5）：LLM 客户端不可达 → 退化为词法单信号（记录告警）；
词法仍无法判定 → vague。捕获流程绝不因路由模块失败而阻塞。

人工兜底：vague 条目 track 保持 unrouted；调用方据此向 review_queue 入队 action='classify'
（机制见 ingest.ingest_with_routing）。

无第三方依赖：OllamaClient 走 stdlib urllib；LexicalRouter 自实现 TF-IDF。
所有阈值走 zkc/tuning.py，禁止裸数字。
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from . import tuning

# ----------------------------------------------------------------- 常量（非阈值，允许模块级）
DEFAULT_LLM_MODEL = "qwen2.5-coder:1.5b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
VAGUE = "unrouted"  # 弃权/模糊在 node.track 上的落点（需人工定轨）
# 词法语料持久化路径（本地优先离线；LexicalRouter 冷启动靠它逐渐自动化）
DEFAULT_LEXICAL_CORPUS_PATH = "data/lexical_corpus.json"

SYSTEM_PROMPT = (
    "你是 ZKC 双轨分类器。只输出 JSON："
    '{"track":"static|dynamic|vague","confidence":0到1,"reason":"一句话"}。'
    "track 定义："
    "static=客观事实/时间线/长生命周期（此刻可信、未来可更新）；"
    "dynamic=当下行动/短生命周期/易腐化（此刻有用、快速衰减）；"
    "vague=不确定/含糊/需再确认/未想清楚。"
    "若信息不足以判断或表述含糊，track 必须为 vague。不要猜测。"
)


# ----------------------------------------------------------------- 信号 A：LLM 客户端（可插拔）
class ChatClient(ABC):
    """LLM 推理客户端的统一接口；测试用 FakeClient 注入，避免依赖 Ollama/网络。"""

    @abstractmethod
    def chat_json(self, system: str, user: str) -> Optional[dict]:
        """返回解析后的 JSON dict；失败/不可达返回 None。"""
        ...

    def health(self) -> bool:
        """客户端是否可达。默认 True；OllamaClient 走真实探测。
        route_text 在线模式下会用它自动降级为离线兜底（不变量 5：本地优先离线）。"""
        return True


class OllamaClient(ChatClient):
    """本地 Ollama /api/chat（stdlib urllib，零依赖）。超时由调用方决定。"""

    def __init__(self, model: str = DEFAULT_LLM_MODEL, url: str = DEFAULT_OLLAMA_URL,
                 timeout: float = 120.0):
        self.model = model
        self.base_url = url.rstrip("/")
        self.url = self.base_url + "/api/chat"
        self.timeout = timeout

    def health(self) -> bool:
        """GET /api/tags 探活；不可达返回 False（交给 route_text 离线兜底）。"""
        try:
            req = urllib.request.Request(self.base_url + "/api/tags")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def chat_json(self, system: str, user: str) -> Optional[dict]:
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        }).encode()
        req = urllib.request.Request(
            self.url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None  # 离线/不可达 → 信号缺失（交由 route_text 离线兜底）
        content = data.get("message", {}).get("content", "")
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


class DecisionRouter:
    """信号 A：LLM-as-judge 轨道判定。模型可替换，语义归 ZKC（SYSTEM_PROMPT）。"""

    def __init__(self, client: ChatClient, gate: Optional[float] = None):
        self.client = client
        self.gate = tuning.get("ROUTING_LLM_CONF_GATE") if gate is None else gate

    def predict(self, text: str) -> tuple[Optional[str], float]:
        """返回 (track|None, confidence)。track∈{static,dynamic,vague}；None=解析失败。"""
        obj = self.client.chat_json(SYSTEM_PROMPT, text)
        if not isinstance(obj, dict):
            return None, 0.0
        track = obj.get("track")
        try:
            conf = float(obj.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        if track not in ("static", "dynamic", "vague"):
            track = None
        return track, conf


# ----------------------------------------------------------------- 信号 B：词法 TF-IDF 三路（embedding-free）
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0
    n = len(tokens) or 1
    return {t: (c / n) * idf.get(t, 0.0) for t, c in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class LexicalRouter:
    """信号 B：零依赖 TF-IDF 三路。fit 于标注集后按类质心余弦分类；低于门槛→vague。

    冷启动（未 fit 或样本不足）→ predict 返回 (None, 0.0)，即「无法判定」，
    由 route_text 转为 vague→人工（安全欠覆盖）。随人工定轨积累样本逐渐自动化。
    """

    def __init__(self, gate: Optional[float] = None, min_examples_per_class: int = 3):
        self.gate = tuning.get("ROUTING_LEXICAL_CONF_GATE") if gate is None else gate
        self.min_examples_per_class = min_examples_per_class
        self._idf: dict[str, float] = {}
        self._centroids: dict[str, dict[str, float]] = {}
        self._fitted = False

    def fit(self, examples: list[tuple[str, str]]) -> "LexicalRouter":
        """examples: [(text, label)]，label∈{static,dynamic,vague}。vague 仅作负例不参与质心。"""
        docs: list[list[str]] = []
        class_tokens: dict[str, list[list[str]]] = {}
        for text, label in examples:
            toks = _tokenize(text)
            if not toks:
                continue
            docs.append(toks)
            if label in ("static", "dynamic"):
                class_tokens.setdefault(label, []).append(toks)

        n_docs = len(docs)
        df: dict[str, int] = {}
        for toks in docs:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self._idf = {t: math.log((n_docs + 1) / (c + 1)) + 1.0
                     for t, c in df.items()}

        self._centroids = {}
        for label, group in class_tokens.items():
            if len(group) < self.min_examples_per_class:
                continue
            summed: dict[str, float] = {}
            for toks in group:
                for term, val in _tfidf_vector(toks, self._idf).items():
                    summed[term] = summed.get(term, 0.0) + val
            k = len(group)
            self._centroids[label] = {t: v / k for t, v in summed.items()}
        self._fitted = bool(self._centroids)
        return self

    @property
    def fitted(self) -> bool:
        return self._fitted

    def predict(self, text: str) -> tuple[Optional[str], float]:
        if not self._fitted:
            return None, 0.0
        vec = _tfidf_vector(_tokenize(text), self._idf)
        best_track, best_sim = None, 0.0
        for label, cen in self._centroids.items():
            sim = _cosine(vec, cen)
            if sim > best_sim:
                best_track, best_sim = label, sim
        if best_track is None or best_sim < self.gate:
            return None, best_sim
        return best_track, best_sim


# ----------------------------------------------------------------- 双信号合成
@dataclass
class RoutingResult:
    """单次分流结果。track=unrouted 即「弃权/模糊→人工兜底」。"""
    track: str                       # static | dynamic | unrouted
    confidence: float                # 提交时取两信号较小置信；弃权时为 LLM 置信
    llm_track: Optional[str]         # DecisionRouter 原始判定（含 vague/None）
    llm_conf: float
    lexical_track: Optional[str]
    lexical_conf: float
    source: str                      # dual-agree | llm-only | lexical-only | abstain-*
    aborted: Optional[str] = None    # 弃权原因（None=已提交真实轨道）


def route_text(
    text: str,
    decision_router: DecisionRouter,
    lexical_router: Optional[LexicalRouter] = None,
    *,
    llm_available: bool = True,
    require_dual_signal: Optional[bool] = None,
) -> RoutingResult:
    """双信号合成分流。见模块 docstring 的弃权规则与离线兜底。"""
    if require_dual_signal is None:
        require_dual_signal = tuning.get("ROUTING_REQUIRE_DUAL_SIGNAL")

    # —— 自动离线探测（不变量 5：本地优先离线）——
    # 调用方声明 llm_available=True 但客户端实际不可达 → 自动降级离线兜底，
    # 捕获流程绝不因路由模块失败而阻塞。
    if llm_available and not decision_router.client.health():
        llm_available = False

    # —— 信号 A（LLM）——
    llm_track, llm_conf = (None, 0.0)
    if llm_available:
        llm_track, llm_conf = decision_router.predict(text)
    gate_llm = decision_router.gate

    # —— 信号 B（词法）——
    lex_track, lex_conf = (None, 0.0)
    if lexical_router is not None:
        lex_track, lex_conf = lexical_router.predict(text)

    # —— 离线兜底：LLM 不可达 → 词法单信号（告警），仍不可判定→vague ——
    if not llm_available:
        if lexical_router is not None and lex_track is not None and lex_conf >= lexical_router.gate:
            return RoutingResult(
                track=lex_track, confidence=lex_conf,
                llm_track=None, llm_conf=0.0,
                lexical_track=lex_track, lexical_conf=lex_conf,
                source="lexical-only", aborted="llm-unavailable-lexical-fallback",
            )
        return RoutingResult(
            track=VAGUE, confidence=0.0,
            llm_track=None, llm_conf=0.0,
            lexical_track=lex_track, lexical_conf=lex_conf,
            source="abstain-offline", aborted="llm-unavailable-and-lexical-undecided",
        )

    # —— LLM 在线，但自身判 vague / 低置信 → 直接弃权（安全）——
    if llm_track in (None, "vague") or llm_conf < gate_llm:
        return RoutingResult(
            track=VAGUE, confidence=llm_conf,
            llm_track=llm_track, llm_conf=llm_conf,
            lexical_track=lex_track, lexical_conf=lex_conf,
            source="abstain-llm", aborted="llm-low-confidence-or-vague",
        )

    # —— LLM 对真实轨道有信心 ——
    lex_gate = lexical_router.gate if lexical_router is not None else 0.0
    if require_dual_signal and lexical_router is not None:
        if lex_track is not None and lex_conf >= lex_gate and lex_track == llm_track:
            return RoutingResult(
                track=llm_track, confidence=min(llm_conf, lex_conf),
                llm_track=llm_track, llm_conf=llm_conf,
                lexical_track=lex_track, lexical_conf=lex_conf,
                source="dual-agree", aborted=None,
            )
        # 双信号要求下：词法无法判定或两信号不一致 → 安全弃权
        return RoutingResult(
            track=VAGUE, confidence=llm_conf,
            llm_track=llm_track, llm_conf=llm_conf,
            lexical_track=lex_track, lexical_conf=lex_conf,
            source="abstain-disagree", aborted="signals-disagree-or-lexical-undecided",
        )

    # —— 无词法交叉验证（未启用 require_dual 或 lexical_router 未提供）→ 单信号提交（降级）——
    return RoutingResult(
        track=llm_track, confidence=llm_conf,
        llm_track=llm_track, llm_conf=llm_conf,
        lexical_track=lex_track, lexical_conf=lex_conf,
        source="llm-only", aborted="no-lexical-crosscheck",
    )


# ----------------------------------------------------------------- 词法语料持久化（LexicalRouter 冷启动学习闭环）
def save_lexical_corpus(path: str, examples: list[tuple[str, str]]) -> None:
    """持久化标注语料 [(text, label)]，label∈{static,dynamic,vague}。本地优先离线。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            [{"text": t, "label": l} for t, l in examples],
            f, ensure_ascii=False, indent=2,
        )


def load_lexical_corpus(path: str) -> list[tuple[str, str]]:
    """读取标注语料；文件不存在返回空列表（冷启动起点）。"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [(row["text"], row["label"]) for row in data]
