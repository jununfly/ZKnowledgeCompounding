"""ZKC · 复利度量面板（P5.2，生产落地 spike-07）。

五个度量（口径见 PRD § / 架构 §；spike-07 已验证）——
  连接密度 connection_density / 复用率 reuse_rate / 方法论产出 methodology_output /
  衰减可控 decay_controllability / 复利系数 compounding_factor。

设计（沿用 load_schedulable 的 seam）：
  - 纯函数层只吃 ``MetricInputs``（普通数据快照），无 DB/仓库依赖 → 可脱离存储单测；
  - ``Storage.load_metric_inputs()`` 按后端把数据捞成 MetricInputs（PG 跑 SQL、内存跑 Python）；
  - ``metrics_report(store)`` = 快照 + 纯函数合成。
阈值 / 权重 / 目标**全部走 zkc.tuning**（P1.4 铁律：禁止裸数字）。

对空库安全：除零一律返回 0.0 / 0，不抛异常。
"""
from __future__ import annotations

from dataclasses import dataclass

from . import tuning
from .repository.models import MetricInputs


# ---------------------------------------------------------------- 纯函数度量

def connection_density(inp: MetricInputs) -> float:
    """动态节点中，至少被一条 reverse_link/derived_from 边触达的比例。"""
    dyn = {nid for (nid, track, _d, _a) in inp.nodes if track == "dynamic"}
    if not dyn:
        return 0.0
    connected = set()
    for (src, dst, kind) in inp.edges:
        if kind in ("reverse_link", "derived_from"):
            if src in dyn:
                connected.add(src)
            if dst in dyn:
                connected.add(dst)
    return len(connected) / len(dyn)


def reuse_rate(inp: MetricInputs) -> tuple[float, float]:
    """返回 (被引用 claim 占比, 平均引用强度)。

    被复用 = 出现在 citation 表 cited_claim_id 的 claim；强度 = citation 总数 / claim 总数。
    """
    total = len(inp.claim_evidence)
    if total == 0:
        return 0.0, 0.0
    cited = len(set(inp.citations))
    rate = cited / total
    per = len(inp.citations) / total
    return rate, per


def methodology_output(inp: MetricInputs) -> int:
    """由结合算子(combine)产出的建模/方法论条目数（artifact_evidence 已只含 combine 产物）。"""
    return len(inp.artifact_evidence)


def decay_controllability(inp: MetricInputs, rot_threshold: float | None = None) -> float:
    """到期(decay>=rot)动态节点中，被蒸馏/结合引用或已归档的比例。

    「被处理」= 其 id 出现在某 claim / artifact 的 evidence_refs，或已 archived。
    注：本指标成立前提是注意力预算满足 n/(0.6×interval)（R4，节点 1-8-6）；预算不满足时
    该比例预期偏低属供给问题而非指标问题——此处只算原始 handled 比例。
    """
    rot = rot_threshold if rot_threshold is not None else tuning.get("ROT_THRESHOLD")
    expired = {nid for (nid, _t, decay, _a) in inp.nodes
               if _t == "dynamic" and decay is not None and decay >= rot}
    if not expired:
        return 0.0
    handled: set = set()
    for refs in inp.claim_evidence:
        handled.update(refs)
    for refs in inp.artifact_evidence:
        handled.update(refs)
    for (nid, _t, _d, archived) in inp.nodes:
        if archived:
            handled.add(nid)
    handled_expired = expired & handled
    return len(handled_expired) / len(expired)


def compounding_factor(
    cd: float, rr: float, mo: int, dc: float,
    weights: tuple[float, float, float, float] | None = None,
    method_target: float | None = None,
) -> float:
    """四项归一化后的加权合成。methodology_output 按目标值饱和归一到 [0,1]。"""
    if weights is None:
        weights = (
            tuning.get("METRIC_W_DENSITY"), tuning.get("METRIC_W_REUSE"),
            tuning.get("METRIC_W_METHOD"), tuning.get("METRIC_W_DECAY"),
        )
    if method_target is None:
        method_target = tuning.get("METRIC_METHOD_TARGET")
    mo_norm = min(1.0, mo / method_target) if method_target else 0.0
    return weights[0] * cd + weights[1] * rr + weights[2] * mo_norm + weights[3] * dc


@dataclass
class MetricReport:
    connection_density: float
    reuse_rate: float
    citations_per_claim: float
    methodology_output: int
    decay_controllability: float
    compounding_factor: float


def build_report(inp: MetricInputs) -> MetricReport:
    cd = connection_density(inp)
    rr, per = reuse_rate(inp)
    mo = methodology_output(inp)
    dc = decay_controllability(inp)
    cf = compounding_factor(cd, rr, mo, dc)
    return MetricReport(cd, rr, per, mo, dc, cf)


def build_report_dict(inp: MetricInputs) -> dict:
    r = build_report(inp)
    return {
        "connection_density": round(r.connection_density, 4),
        "reuse_rate": round(r.reuse_rate, 4),
        "citations_per_claim": round(r.citations_per_claim, 4),
        "methodology_output": r.methodology_output,
        "decay_controllability": round(r.decay_controllability, 4),
        "compounding_factor": round(r.compounding_factor, 4),
    }


# ---------------------------------------------------------------- 存储编排层

def metrics_report(store) -> dict:
    """从 Storage 取快照并合成五度量（含复利系数）。"""
    inp = store.load_metric_inputs()
    return build_report_dict(inp)
