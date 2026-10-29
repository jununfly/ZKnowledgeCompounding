"""Compounding metrics (T7.1) over the ZKC schema, plus T6.2 citation instrumentation.

Metric口径 (calibration):
  - 连接密度 connection_density: 动态节点中，至少有一条 reverse_link/derived_from 边触达的比例。
  - 复用率 reuse_rate: 被后续条目引用(通过 citation 表)的 claim 占比；citations_per_claim 为平均引用强度。
  - 方法论产出 methodology_output: 由结合算子(combine transform)产出的建模/方法论条目数。
  - 衰减可控 decay_controllability: 到期(decay>=ROT)动态节点中，被蒸馏/结合引用 或 已归档 的比例。
  - 复利系数 compounding_factor: 上述四项归一化后的加权合成（权重/目标值待校准，见 README）。

所有函数对空库安全（除零返回 0.0），不抛异常。
"""
from dataclasses import dataclass

# mirror architecture §6.3 thresholds
ROT_THRESHOLD = 0.9
# methodology_output 归一化目标：达到该产出数即记满分 1.0（待校准）
METHOD_TARGET_DEFAULT = 10.0
DEFAULT_WEIGHTS = (0.25, 0.25, 0.25, 0.25)  # (density, reuse, method, decay)


def connection_density(cur) -> float:
    cur.execute(
        """
        SELECT
          (SELECT count(DISTINCT n.id)::float
             FROM node n JOIN edge e ON (e.src = n.id OR e.dst = n.id)
            WHERE n.track = 'dynamic'
              AND e.kind IN ('reverse_link', 'derived_from')) AS connected,
          (SELECT count(*)::float FROM node WHERE track = 'dynamic') AS total
        """
    )
    connected, total = cur.fetchone()
    return (connected / total) if total else 0.0


def reuse_rate(cur):
    """Returns (rate, citations_per_claim)."""
    cur.execute(
        """
        SELECT
          (SELECT count(DISTINCT cited_claim_id)::float FROM citation) AS cited,
          (SELECT count(*)::float FROM meta_claim) AS total,
          (SELECT count(*)::float FROM citation) AS citations
        """
    )
    cited, total, citations = cur.fetchone()
    rate = (cited / total) if total else 0.0
    per = (citations / total) if total else 0.0
    return rate, per


def methodology_output(cur) -> int:
    cur.execute(
        """
        SELECT count(*) FROM modeling_artifact ma
        JOIN transform t ON t.id = ma.produced_by
        WHERE t.kind = 'combine'
        """
    )
    return cur.fetchone()[0]


def decay_controllability(cur, rot_threshold: float = ROT_THRESHOLD) -> float:
    cur.execute(
        """
        WITH handled AS (
          SELECT unnest(evidence_refs) AS nid FROM meta_claim
          UNION
          SELECT unnest(evidence_refs) AS nid FROM modeling_artifact
          UNION
          SELECT id AS nid FROM node WHERE archived_at IS NOT NULL
        ),
        expired AS (
          SELECT id FROM node WHERE track = 'dynamic' AND decay_score >= %s
        )
        SELECT
          (SELECT count(*)::float FROM expired e JOIN handled h ON h.nid = e.id) AS handled_expired,
          (SELECT count(*)::float FROM expired) AS expired_total
        """,
        (rot_threshold,),
    )
    handled, total = cur.fetchone()
    return (handled / total) if total else 0.0


@dataclass
class CompoundingReport:
    connection_density: float
    reuse_rate: float
    citations_per_claim: float
    methodology_output: int
    decay_controllability: float
    compounding_factor: float


def compounding_factor(cur, weights=DEFAULT_WEIGHTS,
                       method_target: float = METHOD_TARGET_DEFAULT) -> float:
    cd = connection_density(cur)
    rr, _ = reuse_rate(cur)
    mo = methodology_output(cur)
    dc = decay_controllability(cur)
    mo_norm = min(1.0, mo / method_target)
    return weights[0] * cd + weights[1] * rr + weights[2] * mo_norm + weights[3] * dc


def report(cur, weights=DEFAULT_WEIGHTS,
           method_target: float = METHOD_TARGET_DEFAULT) -> CompoundingReport:
    cd = connection_density(cur)
    rr, per = reuse_rate(cur)
    mo = methodology_output(cur)
    dc = decay_controllability(cur)
    mo_norm = min(1.0, mo / method_target)
    cf = weights[0] * cd + weights[1] * rr + weights[2] * mo_norm + weights[3] * dc
    return CompoundingReport(cd, rr, per, mo, dc, cf)
