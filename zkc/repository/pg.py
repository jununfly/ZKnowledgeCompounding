"""ZKC · Postgres 实现（P1.2）：raw SQL + psycopg，不引入 SQLAlchemy ORM。

承接 1-2-4 决策（不回迁 Alembic）与 1-2-5 约束（seam = raw SQL + repository）。
psycopg 懒加载于 connect()；本模块 import 不依赖 DB 驱动，便于无 DB 单测导入。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from .. import tuning
from .connection import connect
from .errors import ConcurrentModification
from .models import (
    AttentionObservation,
    Claim,
    Context,
    Edge,
    MetricInputs,
    Node,
    ReviewItem,
    SchedulableNode,
)
from .protocols import (
    AttentionRepository,
    ClaimRepository,
    ContextRepository,
    EdgeRepository,
    NodeRepository,
    ReviewQueueRepository,
    Storage,
)


def _vec_to_sql(emb) -> Optional[str]:
    if emb is None:
        return None
    return "[" + ",".join(repr(float(x)) for x in emb) + "]"


def _sql_to_vec(val):
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        return [float(x) for x in val]
    s = str(val).strip()
    if s.startswith("["):
        s = s[1:]
    if s.endswith("]"):
        s = s[:-1]
    return [float(x) for x in s.split(",")] if s.strip() else []


class PgNodeRepository(NodeRepository):
    def __init__(self, conn, lock_hook=None) -> None:
        self._conn = conn
        # 测试/并发探针钩子：在「加行锁前」调用一次（默认 None 不触发）。
        # 并发测试通过它把两条写事务同步到同一屏障，确保 FOR UPDATE 之前双方都已
        # 就位，从而确定性地暴露无锁时的历史错乱。
        self._lock_hook = lock_hook

    # append-only 版本链：在「已持行锁」前提下把当前 node 行镜像进 node_history
    # （tx_to=clock_timestamp() 闭合）。两步同处一个事务：并发写者因 FOR UPDATE 阻塞
    # 到本事务提交，从而读到正确旧版再快照，杜绝「两事务同读旧态各自快照」导致历史错乱 /
    # 丢失更新（修复 2026-10-31 收尾时标注的并发竞态）。
    # 注：tx_from / tx_to 用 clock_timestamp()（真实执行时刻，随提交顺序单调递增），
    # 而非 now()（事务起始时刻）。否则「先开始但后提交」的事务会得到更早的 tx_from，
    # 使当前态在 history() 排序中落在历史版本之前，破坏「当前态恒为最后版本」不变量。
    def _locked_snapshot(self, cur, node_id: UUID) -> int:
        # 1) 锁住行并读出当前版本号（OCC 期望版本来源）；并发写者在此阻塞直到本事务提交
        cur.execute(
            "SELECT id, version_seq FROM public.node WHERE id=%(id)s FOR UPDATE",
            dict(id=node_id),
        )
        row = cur.fetchone()
        # 2) 快照当前行进历史表（tx_to=clock_timestamp() 闭合），连同 version_seq 一并镜像
        cur.execute(
            """
            INSERT INTO public.node_history
                (id, track, routing_confidence, title, content, valid_from, valid_to,
                 tx_from, decay_score, review_interval, last_reviewed_at,
                 attention_signal, created_at, embedding, archived_at,
                 baseline_interval, interval_source, tx_to, version_seq)
            SELECT id, track, routing_confidence, title, content, valid_from, valid_to,
                   tx_from, decay_score, review_interval, last_reviewed_at,
                   attention_signal, created_at, embedding, archived_at,
                   baseline_interval, interval_source, clock_timestamp(), version_seq
            FROM public.node WHERE id=%(id)s
            """,
            dict(id=node_id),
        )
        return int(row["version_seq"])

    def save(self, node: Node) -> Node:
        cur = self._conn.cursor(row_factory=dict_row)
        if node.id is None:
            cur.execute(
                """
                INSERT INTO public.node
                    (track, routing_confidence, title, content, valid_from, valid_to,
                     decay_score, review_interval, last_reviewed_at, attention_signal,
                     embedding, archived_at, baseline_interval, interval_source)
                VALUES (%(track)s, %(rc)s, %(title)s, %(content)s, %(vf)s, %(vt)s,
                        %(decay)s, %(ri)s, %(lr)s, %(att)s, %(emb)s::vector,
                        %(arch)s, %(bi)s, %(isrc)s)
                RETURNING id, created_at, tx_from, version_seq
                """,
                dict(
                    track=node.track, rc=node.routing_confidence, title=node.title,
                    content=node.content, vf=node.valid_from, vt=node.valid_to,
                    decay=node.decay_score, ri=node.review_interval, lr=node.last_reviewed_at,
                    att=node.attention_signal, emb=_vec_to_sql(node.embedding),
                    arch=node.archived_at, bi=node.baseline_interval, isrc=node.interval_source,
                ),
            )
            r = cur.fetchone()
            node.id, node.created_at, node.tx_from, node.version_seq = (
                r["id"], r["created_at"], r["tx_from"], r["version_seq"])
        else:
            params = dict(
                id=node.id, track=node.track, rc=node.routing_confidence, title=node.title,
                content=node.content, vf=node.valid_from, vt=node.valid_to,
                decay=node.decay_score, ri=node.review_interval, lr=node.last_reviewed_at,
                att=node.attention_signal, emb=_vec_to_sql(node.embedding),
                arch=node.archived_at, bi=node.baseline_interval, isrc=node.interval_source,
            )
            # append-only 版本链 + OCC：单事务内「FOR UPDATE 锁行 → 快照 → 更新当前行」。
            # 并发安全由悲观行锁 FOR UPDATE 保证（串行化，last-writer-wins 不变，不破坏单写者语义）。
            # version_seq 随每次写自增；WHERE 带 version_seq=锁后当前版本（expect 取自已持锁的
            # _locked_snapshot 返回值）——悲观锁下该值恒等于 DB 当前版本，故永不冲突。
            # 严格 OCC 能力（基于过期版本拒绝写）保留给：update_decay/set_interval 的显式
            # version_seq 参数、以及 claim/context 的 upsert（用调用方持有的版本做校验）。
            if self._lock_hook is not None:
                self._lock_hook()
            expect = self._locked_snapshot(cur, node.id)
            cur.execute(
                """
                UPDATE public.node SET
                    track=%(track)s, routing_confidence=%(rc)s, title=%(title)s,
                    content=%(content)s, valid_from=%(vf)s, valid_to=%(vt)s,
                    decay_score=%(decay)s, review_interval=%(ri)s,
                    last_reviewed_at=%(lr)s, attention_signal=%(att)s,
                    embedding=%(emb)s::vector, archived_at=%(arch)s,
                    baseline_interval=%(bi)s, interval_source=%(isrc)s,
                    version_seq = version_seq + 1,
                    tx_from=clock_timestamp()
                WHERE id=%(id)s AND version_seq=%(expect)s
                RETURNING id, created_at, tx_from, version_seq
                """,
                dict(params, expect=expect),
            )
            r = cur.fetchone()
            node.id, node.created_at, node.tx_from, node.version_seq = (
                r["id"], r["created_at"], r["tx_from"], r["version_seq"])
            node.tx_to = None
        self._conn.commit()
        return node

    def get(self, node_id: UUID) -> Node | None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute("SELECT * FROM public.node WHERE id=%(id)s", dict(id=node_id))
        row = cur.fetchone()
        return self._row_to_node(row) if row else None

    def history(self, node_id: UUID) -> list[Node]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT * FROM public.node_history WHERE id=%(id)s
            UNION ALL
            SELECT * FROM public.node WHERE id=%(id)s
            ORDER BY tx_from
            """,
            dict(id=node_id),
        )
        return [self._row_to_node(r) for r in cur.fetchall()]

    def list_by_track(self, track: str) -> list[Node]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute("SELECT * FROM public.node WHERE track=%(t)s", dict(t=track))
        return [self._row_to_node(r) for r in cur.fetchall()]

    def list_due_for_review(self, as_of: datetime) -> list[Node]:
        # 阈值走 tuning（禁止裸数字，P1.4 铁律）：SURFACE_THRESHOLD=0.6 进入注意力
        surface = tuning.get("SURFACE_THRESHOLD")
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT * FROM public.node
            WHERE decay_score >= %(surface)s
              AND review_interval IS NOT NULL
              AND last_reviewed_at IS NOT NULL
              AND (last_reviewed_at + review_interval) <= %(as_of)s
            """,
            dict(surface=surface, as_of=as_of),
        )
        return [self._row_to_node(r) for r in cur.fetchall()]

    def update_decay(
        self, node_id: UUID, decay_score: float, version_seq: int | None = None
    ) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        if self._lock_hook is not None:
            self._lock_hook()
        # 轻量路径（c2 决议 A-1a，2026-10-31）：decay_score 是 compute_decay_score 的派生
        # 投影（由 last_reviewed_at+review_interval+now 可重算），并非事实 —— 不写 node_history、
        # 不 bump tx_from（tx_from 始终标记「上次事实变更」），仅更新派生列并自增 version_seq
        # 保活 OCC。FOR UPDATE 仍持行锁，保证并发写者串行（避免「两事务同读旧态各自更新」丢失更新）。
        cur.execute(
            "SELECT id, version_seq FROM public.node WHERE id=%(id)s FOR UPDATE",
            dict(id=node_id),
        )
        row = cur.fetchone()
        # version_seq 由调用方持有时做严格 OCC；为 None（兼容旧调用）仅自增，
        # 退化由 FOR UPDATE 悲观锁串行兜底。expect 优先用调用方版本，否则用锁后当前版。
        expect = version_seq if version_seq is not None else int(row["version_seq"])
        occ = "" if version_seq is None else " AND version_seq=%(expect)s"
        cur.execute(
            f"UPDATE public.node SET decay_score=%(d)s, version_seq = version_seq + 1 "
            f"WHERE id=%(id)s{occ} RETURNING version_seq",
            dict(d=decay_score, id=node_id, expect=expect),
        )
        r = cur.fetchone()
        if version_seq is not None and r is None:
            raise ConcurrentModification(
                f"node {node_id} decay 更新版本冲突：期望 version_seq={version_seq}"
            )
        self._conn.commit()

    def set_interval(
        self,
        node_id: UUID,
        interval: timedelta,
        source: str,
        reason: str,
        version_seq: int | None = None,
    ) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        if self._lock_hook is not None:
            self._lock_hook()
        current = self._locked_snapshot(cur, node_id)
        expect = version_seq if version_seq is not None else current
        occ = "" if version_seq is None else " AND version_seq=%(expect)s"
        cur.execute(
            f"""
            UPDATE public.node SET review_interval=%(iv)s, interval_source=%(src)s,
                   version_seq = version_seq + 1,
                   tx_from=clock_timestamp()
            WHERE id=%(id)s{occ} RETURNING version_seq
            """,
            dict(iv=interval, src=source, id=node_id, expect=expect),
        )
        r = cur.fetchone()
        if version_seq is not None and r is None:
            raise ConcurrentModification(
                f"node {node_id} interval 设置版本冲突：期望 version_seq={version_seq}"
            )
        self._conn.commit()

    def set_baseline_interval(
        self,
        node_id: UUID,
        interval: timedelta,
        source: str,
        reason: str,
    ) -> None:
        """L1 基线赋值：baseline_interval 与 review_interval 此刻一致（均来自 L1 估算）。"""
        cur = self._conn.cursor(row_factory=dict_row)
        if self._lock_hook is not None:
            self._lock_hook()
        self._locked_snapshot(cur, node_id)
        cur.execute(
            """
            UPDATE public.node SET baseline_interval=%(iv)s, review_interval=%(iv)s,
                   interval_source=%(src)s, version_seq = version_seq + 1,
                   tx_from=clock_timestamp()
            WHERE id=%(id)s RETURNING version_seq
            """,
            dict(iv=interval, src=source, id=node_id),
        )
        self._conn.commit()

    def audit_interval(
        self,
        node_id: UUID,
        kind: str,
        old_days: float | None,
        new_days: float,
        reason: str,
        produced_by: UUID | None = None,
    ) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "INSERT INTO public.interval_adjustment "
            "(node_id, kind, old_days, new_days, reason, produced_by) VALUES (%s,%s,%s,%s,%s,%s)",
            (node_id, kind, old_days, new_days, reason, produced_by),
        )
        self._conn.commit()

    def mark_reviewed(self, node_id: UUID, at: datetime) -> None:
        """复审触碰：复位衰减时钟（last_reviewed_at=at, decay_score=0）。

        轻量路径（与 update_decay 一致）：decay_score 是派生投影，不写 node_history、
        不 bump tx_from；仅更新派生列并自增 version_seq 保活 OCC。
        """
        cur = self._conn.cursor(row_factory=dict_row)
        if self._lock_hook is not None:
            self._lock_hook()
        cur.execute(
            "UPDATE public.node SET last_reviewed_at=%(at)s, decay_score=0,"
            " version_seq = version_seq + 1 WHERE id=%(id)s RETURNING version_seq",
            dict(at=at, id=node_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_node(row) -> Node:
        d = dict(row)
        return Node(
            id=d["id"], track=d["track"], routing_confidence=d.get("routing_confidence"),
            title=d["title"], content=d.get("content"),
            valid_from=d.get("valid_from"), valid_to=d.get("valid_to"),
            tx_from=d.get("tx_from"), tx_to=d.get("tx_to"),
            decay_score=d["decay_score"], review_interval=d.get("review_interval"),
            last_reviewed_at=d.get("last_reviewed_at"),
            attention_signal=d.get("attention_signal", 0.0),
            embedding=_sql_to_vec(d.get("embedding")), archived_at=d.get("archived_at"),
            baseline_interval=d.get("baseline_interval"),
            interval_source=d.get("interval_source", "auto"),
            version_seq=d.get("version_seq", 1),
            created_at=d.get("created_at"),
        )


class PgClaimRepository(ClaimRepository):
    def __init__(self, conn) -> None:
        self._conn = conn

    def save(self, claim: Claim) -> Claim:
        cur = self._conn.cursor(row_factory=dict_row)
        if claim.id is None:
            cur.execute(
                """
                INSERT INTO public.meta_claim
                    (statement, level, confidence, evidence_refs, produced_by, revises,
                     faithfulness_status, faithfulness_route, judge_raw, judge_model,
                     human_verdict, human_verdict_at, version_seq)
                VALUES (%(st)s, %(lv)s, %(cf)s, %(ev)s::uuid[], %(pb)s, %(rv)s,
                        %(fs)s, %(fr)s, %(jr)s, %(jm)s, %(hv)s, %(hva)s, 1)
                RETURNING id, created_at, version_seq
                """,
                dict(
                    st=claim.statement, lv=claim.level, cf=claim.confidence,
                    ev=claim.evidence_refs, pb=claim.produced_by, rv=claim.revises,
                    fs=claim.faithfulness_status, fr=claim.faithfulness_route,
                    jr=Json(claim.judge_raw) if claim.judge_raw is not None else None, jm=claim.judge_model,
                    hv=claim.human_verdict, hva=claim.human_verdict_at,
                ),
            )
            r = cur.fetchone()
            claim.id, claim.created_at, claim.version_seq = (
                r["id"], r["created_at"], r["version_seq"])
        else:
            cur.execute(
                """
                INSERT INTO public.meta_claim
                    (id, statement, level, confidence, evidence_refs, produced_by, revises,
                     faithfulness_status, faithfulness_route, judge_raw, judge_model,
                     human_verdict, human_verdict_at, version_seq)
                VALUES (%(id)s, %(st)s, %(lv)s, %(cf)s, %(ev)s::uuid[], %(pb)s, %(rv)s,
                        %(fs)s, %(fr)s, %(jr)s, %(jm)s, %(hv)s, %(hva)s, 1)
                ON CONFLICT (id) DO UPDATE SET
                    statement=EXCLUDED.statement, level=EXCLUDED.level,
                    confidence=EXCLUDED.confidence, evidence_refs=EXCLUDED.evidence_refs,
                    produced_by=EXCLUDED.produced_by, revises=EXCLUDED.revises,
                    faithfulness_status=EXCLUDED.faithfulness_status,
                    faithfulness_route=EXCLUDED.faithfulness_route,
                    judge_raw=EXCLUDED.judge_raw, judge_model=EXCLUDED.judge_model,
                    human_verdict=EXCLUDED.human_verdict,
                    human_verdict_at=EXCLUDED.human_verdict_at,
                    version_seq = meta_claim.version_seq + 1
                WHERE meta_claim.version_seq = %(expect)s
                RETURNING id, created_at, version_seq
                """,
                dict(
                    id=claim.id, st=claim.statement, lv=claim.level, cf=claim.confidence,
                    ev=claim.evidence_refs, pb=claim.produced_by, rv=claim.revises,
                    fs=claim.faithfulness_status, fr=claim.faithfulness_route,
                    jr=Json(claim.judge_raw) if claim.judge_raw is not None else None, jm=claim.judge_model,
                    hv=claim.human_verdict, hva=claim.human_verdict_at,
                    expect=claim.version_seq,
                ),
            )
            r = cur.fetchone()
            if r is None:
                raise ConcurrentModification(
                    f"claim {claim.id} 版本冲突：期望 version_seq={claim.version_seq}，"
                    f"但当前态已被并发写推进（OCC 拒绝过期写入）"
                )
            claim.id, claim.created_at, claim.version_seq = (
                r["id"], r["created_at"], r["version_seq"])
        self._conn.commit()
        return claim

    def get(self, claim_id: UUID) -> Claim | None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute("SELECT * FROM public.meta_claim WHERE id=%(id)s", dict(id=claim_id))
        row = cur.fetchone()
        return self._row_to_claim(row) if row else None

    def list_by_evidence(self, node_id: UUID) -> list[Claim]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "SELECT * FROM public.meta_claim WHERE %(nid)s::uuid = ANY(evidence_refs)",
            dict(nid=node_id),
        )
        return [self._row_to_claim(r) for r in cur.fetchall()]

    @staticmethod
    def _row_to_claim(row) -> Claim:
        d = dict(row)
        return Claim(
            id=d["id"], statement=d["statement"], level=d.get("level"),
            confidence=d.get("confidence"), evidence_refs=list(d.get("evidence_refs") or []),
            produced_by=d.get("produced_by"), revises=d.get("revises"),
            faithfulness_status=d.get("faithfulness_status"),
            faithfulness_route=d.get("faithfulness_route"),
            judge_raw=d.get("judge_raw"), judge_model=d.get("judge_model"),
            human_verdict=d.get("human_verdict"), human_verdict_at=d.get("human_verdict_at"),
            version_seq=d.get("version_seq", 1),
            created_at=d.get("created_at"),
        )


class PgEdgeRepository(EdgeRepository):
    def __init__(self, conn) -> None:
        self._conn = conn

    def link(self, src, dst, kind, weight=None, produced_by=None) -> Edge:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            INSERT INTO public.edge (src, dst, kind, weight, produced_by)
            VALUES (%(src)s, %(dst)s, %(kind)s, %(w)s, %(pb)s)
            RETURNING id
            """,
            dict(src=src, dst=dst, kind=kind, w=weight, pb=produced_by),
        )
        eid = cur.fetchone()["id"]
        self._conn.commit()
        return Edge(id=eid, src=src, dst=dst, kind=kind, weight=weight, produced_by=produced_by)

    def list_for_node(self, node_id: UUID) -> list[Edge]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "SELECT id, src, dst, kind, weight, produced_by FROM public.edge "
            "WHERE src=%(nid)s OR dst=%(nid)s",
            dict(nid=node_id),
        )
        return [Edge(id=r["id"], src=r["src"], dst=r["dst"], kind=r["kind"], weight=r["weight"], produced_by=r["produced_by"])
                for r in cur.fetchall()]

    def delete(self, edge_id: UUID) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute("DELETE FROM public.edge WHERE id=%(id)s", dict(id=edge_id))
        self._conn.commit()


class PgContextRepository(ContextRepository):
    def __init__(self, conn) -> None:
        self._conn = conn

    def save(self, context: Context) -> Context:
        cur = self._conn.cursor(row_factory=dict_row)
        if context.id is None:
            cur.execute(
                """
                INSERT INTO public.context (scope, label, title, produced_by, version_seq)
                VALUES (%(sc)s, %(lb)s, %(ti)s, %(pb)s, 1) RETURNING id, version_seq
                """,
                dict(sc=context.scope, lb=context.label, ti=context.title, pb=context.produced_by),
            )
            r = cur.fetchone()
            context.id, context.version_seq = r["id"], r["version_seq"]
        else:
            cur.execute(
                """
                INSERT INTO public.context (id, scope, label, title, produced_by, version_seq)
                VALUES (%(id)s, %(sc)s, %(lb)s, %(ti)s, %(pb)s, 1)
                ON CONFLICT (id) DO UPDATE SET
                    scope=EXCLUDED.scope, label=EXCLUDED.label,
                    title=EXCLUDED.title, produced_by=EXCLUDED.produced_by,
                    version_seq = context.version_seq + 1
                WHERE context.version_seq = %(expect)s
                RETURNING id, version_seq
                """,
                dict(id=context.id, sc=context.scope, lb=context.label,
                     ti=context.title, pb=context.produced_by, expect=context.version_seq),
            )
            r = cur.fetchone()
            if r is None:
                raise ConcurrentModification(
                    f"context {context.id} 版本冲突：期望 version_seq={context.version_seq}"
                )
            context.id, context.version_seq = r["id"], r["version_seq"]
        self._conn.commit()
        return context

    def add_member(self, context_id, node_id, weight=1.0, produced_by=None) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            INSERT INTO public.context_member (context_id, node_id, weight, produced_by)
            VALUES (%(cid)s, %(nid)s, %(w)s, %(pb)s)
            ON CONFLICT (context_id, node_id) DO UPDATE SET weight=EXCLUDED.weight
            """,
            dict(cid=context_id, nid=node_id, w=weight, pb=produced_by),
        )
        self._conn.commit()

    def list_members(self, context_id: UUID) -> list[UUID]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "SELECT node_id FROM public.context_member WHERE context_id=%(cid)s",
            dict(cid=context_id),
        )
        return [r["node_id"] for r in cur.fetchall()]

    def list_for_node(self, node_id: UUID) -> list[Context]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT c.id, c.scope, c.label, c.title, c.produced_by, c.version_seq
            FROM public.context c
            JOIN public.context_member cm ON cm.context_id = c.id
            WHERE cm.node_id = %(nid)s
            """,
            dict(nid=node_id),
        )
        return [Context(id=r["id"], scope=r["scope"], label=r["label"], title=r["title"],
                        produced_by=r["produced_by"], version_seq=r.get("version_seq", 1))
                for r in cur.fetchall()]

    def add_member_human(self, context_id, node_id, weight=1.0) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            INSERT INTO public.context_member (context_id, node_id, weight, produced_by)
            VALUES (%(cid)s, %(nid)s, %(w)s, NULL)
            ON CONFLICT (context_id, node_id) DO UPDATE SET weight=EXCLUDED.weight
            """,
            dict(cid=context_id, nid=node_id, w=weight),
        )
        self._conn.commit()

    def remove_member_human(self, context_id, node_id) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "DELETE FROM public.context_member "
            "WHERE context_id=%(cid)s AND node_id=%(nid)s AND produced_by IS NULL",
            dict(cid=context_id, nid=node_id),
        )
        self._conn.commit()

    def find_higher_dim_for_seed(self, node_id) -> UUID | None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT c.id FROM public.context c
            JOIN public.context_member cm ON cm.context_id = c.id
            WHERE c.scope = 'higher_dim' AND cm.node_id = %(nid)s::uuid
            LIMIT 1
            """,
            dict(nid=str(node_id)),
        )
        r = cur.fetchone()
        return r["id"] if r else None


class PgReviewQueueRepository(ReviewQueueRepository):
    def __init__(self, conn) -> None:
        self._conn = conn

    def enqueue(self, node_id, action, reason=None) -> ReviewItem:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            INSERT INTO public.review_queue (node_id, action, reason)
            VALUES (%(nid)s, %(act)s, %(rs)s) RETURNING id, created_at, resolved
            """,
            dict(nid=node_id, act=action, rs=reason),
        )
        r = cur.fetchone()
        iid, created_at, resolved = r["id"], r["created_at"], r["resolved"]
        self._conn.commit()
        return ReviewItem(id=iid, node_id=node_id, action=action, reason=reason,
                          created_at=created_at, resolved=resolved)

    def pop_open(self, limit=None) -> list[ReviewItem]:
        cur = self._conn.cursor(row_factory=dict_row)
        sql = ("SELECT id, node_id, action, reason, created_at, resolved "
               "FROM public.review_queue WHERE resolved=false ORDER BY created_at")
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur.execute(sql)
        return [self._row_to_item(r) for r in cur.fetchall()]

    def resolve(self, item_id: UUID) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute("UPDATE public.review_queue SET resolved=true WHERE id=%(id)s", dict(id=item_id))
        self._conn.commit()

    def list_open(self) -> list[ReviewItem]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "SELECT id, node_id, action, reason, created_at, resolved "
            "FROM public.review_queue WHERE resolved=false ORDER BY created_at"
        )
        return [self._row_to_item(r) for r in cur.fetchall()]

    @staticmethod
    def _row_to_item(r) -> ReviewItem:
        return ReviewItem(id=r["id"], node_id=r["node_id"], action=r["action"], reason=r["reason"],
                          created_at=r["created_at"], resolved=r["resolved"])


class PgAttentionRepository(AttentionRepository):
    def __init__(self, conn) -> None:
        self._conn = conn

    def record_observation(self, obs: AttentionObservation) -> None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            INSERT INTO public.attention_observation
                (day, pushed, completed, queue_remaining, labeled_completed)
            VALUES (%(day)s::date, %(p)s, %(c)s, %(q)s, %(l)s)
            ON CONFLICT (day) DO UPDATE SET
                pushed=EXCLUDED.pushed, completed=EXCLUDED.completed,
                queue_remaining=EXCLUDED.queue_remaining,
                labeled_completed=EXCLUDED.labeled_completed
            """,
            dict(day=obs.day.date() if isinstance(obs.day, datetime) else obs.day,
                 p=obs.pushed, c=obs.completed,
                 q=obs.queue_remaining, l=obs.labeled_completed),
        )
        self._conn.commit()

    def get(self, day) -> AttentionObservation | None:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "SELECT day, pushed, completed, queue_remaining, labeled_completed "
            "FROM public.attention_observation WHERE day=%(d)s::date",
            dict(d=day.date() if isinstance(day, datetime) else day),
        )
        r = cur.fetchone()
        if not r:
            return None
        return AttentionObservation(day=r["day"], pushed=r["pushed"], completed=r["completed"],
                                    queue_remaining=r["queue_remaining"],
                                    labeled_completed=r["labeled_completed"])

    def list_recent(self, days: int = 30) -> list[AttentionObservation]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT day, pushed, completed, queue_remaining, labeled_completed
            FROM public.attention_observation
            WHERE day >= current_date - %(days)s::int
            ORDER BY day DESC
            """,
            dict(days=days),
        )
        return [AttentionObservation(day=r["day"], pushed=r["pushed"], completed=r["completed"],
                                     queue_remaining=r["queue_remaining"],
                                     labeled_completed=r["labeled_completed"])
                for r in cur.fetchall()]


class PgStorage(Storage):
    def __init__(self, conn=None) -> None:
        self._conn = conn or connect()
        self.nodes = PgNodeRepository(self._conn)
        self.claims = PgClaimRepository(self._conn)
        self.edges = PgEdgeRepository(self._conn)
        self.contexts = PgContextRepository(self._conn)
        self.review_queue = PgReviewQueueRepository(self._conn)
        self.attention = PgAttentionRepository(self._conn)

    def record_transform(self, kind: str, params: dict) -> UUID:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "INSERT INTO public.transform (kind, params) VALUES (%s, %s) RETURNING id",
            (kind, Json(params)),
        )
        tid = cur.fetchone()["id"]
        self._conn.commit()
        return tid

    def load_schedulable(self) -> list[SchedulableNode]:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT
              n.id,
              n.track,
              n.title,
              n.content,
              n.review_interval,
              n.baseline_interval,
              n.interval_source,
              n.archived_at IS NOT NULL AS archived,
              ( EXISTS(SELECT 1 FROM public.meta_claim m
                         WHERE m.evidence_refs @> ARRAY[n.id] LIMIT 1)
                OR EXISTS(SELECT 1 FROM public.modeling_artifact a
                            WHERE a.evidence_refs @> ARRAY[n.id] LIMIT 1)
              ) AS captured,
              (SELECT count(*) FROM public.edge e WHERE e.src = n.id OR e.dst = n.id) AS conn_count,
              (SELECT count(*) FROM public.context_member cm
                 JOIN public.context c ON c.id = cm.context_id
                 WHERE cm.node_id = n.id AND c.scope = 'self_loop') AS self_loop_count,
              (SELECT count(*) FROM public.context_member cm
                 JOIN public.context c ON c.id = cm.context_id
                 WHERE cm.node_id = n.id AND c.scope = 'higher_dim') AS higher_dim_count
            FROM public.node n
            WHERE n.track = 'dynamic' AND n.archived_at IS NULL
            """
        )
        out = []
        for r in cur.fetchall():
            iv = r["review_interval"]
            bi = r["baseline_interval"]
            out.append(SchedulableNode(
                id=r["id"], track=r["track"], title=r["title"], content=r["content"],
                captured=bool(r["captured"]), conn_count=int(r["conn_count"]),
                self_loop_count=int(r["self_loop_count"]),
                higher_dim_count=int(r["higher_dim_count"]),
                interval_days=(iv.total_seconds() / 86400.0) if iv is not None else None,
                baseline_days=(bi.total_seconds() / 86400.0) if bi is not None else None,
                source=r["interval_source"], archived=bool(r["archived"]),
            ))
        return out

    def load_metric_inputs(self) -> MetricInputs:
        """复利度量快照（P5.2）：单游标多查询捞出普通数据，纯函数度量只吃此快照。"""
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT id, track, COALESCE(decay_score, 0) AS decay,
                   (archived_at IS NOT NULL) AS archived
            FROM public.node
            """
        )
        nodes = [(r["id"], r["track"], float(r["decay"]), bool(r["archived"]))
                 for r in cur.fetchall()]
        cur.execute("SELECT src, dst, kind FROM public.edge")
        edges = [(r["src"], r["dst"], r["kind"]) for r in cur.fetchall()]
        cur.execute("SELECT evidence_refs FROM public.meta_claim "
                    "WHERE evidence_refs IS NOT NULL")
        claim_evidence = [list(r["evidence_refs"]) for r in cur.fetchall()]
        cur.execute(
            "SELECT ma.evidence_refs FROM public.modeling_artifact ma "
            "JOIN public.transform t ON t.id = ma.produced_by "
            "WHERE t.kind = 'combine' AND ma.evidence_refs IS NOT NULL"
        )
        artifact_evidence = [list(r["evidence_refs"]) for r in cur.fetchall()]
        cur.execute("SELECT cited_claim_id FROM public.citation")
        citations = [r["cited_claim_id"] for r in cur.fetchall()]
        return MetricInputs(
            nodes=nodes, edges=edges, claim_evidence=claim_evidence,
            artifact_evidence=artifact_evidence, citations=citations,
        )

    def revert_interval_transform(self, transform_id: UUID) -> int:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "SELECT node_id, old_days FROM public.interval_adjustment "
            "WHERE produced_by=%s::uuid ORDER BY created_at DESC",
            (str(transform_id),),
        )
        changes = cur.fetchall()
        for r in changes:
            node_id, old_days = r["node_id"], r["old_days"]
            cur.execute(
                "UPDATE public.node SET review_interval=%s WHERE id=%s",
                (timedelta(days=float(old_days)) if old_days is not None else None,
                 str(node_id)),
            )
        cur.execute("DELETE FROM public.transform WHERE id=%s::uuid", (str(transform_id),))
        self._conn.commit()
        return len(changes)

    def assemble_context(
        self, scope: str, node_ids, title=None, weight: float = 1.0
    ) -> tuple[UUID, UUID]:
        if scope not in ("self_loop", "higher_dim"):
            raise ValueError(f"invalid scope: {scope}")
        tid = self.record_transform(
            "context_assembly", {"scope": scope, "node_ids": [str(n) for n in node_ids]}
        )
        ctx = self.contexts.save(Context(scope=scope, title=title, produced_by=tid))
        for nid in node_ids:
            self.contexts.add_member(ctx.id, nid, weight, produced_by=tid)
        return (ctx.id, tid)

    def revert_assembly(self, transform_id: UUID) -> int:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            "SELECT count(*) AS n FROM public.context WHERE produced_by=%(tid)s::uuid",
            dict(tid=str(transform_id)),
        )
        n = cur.fetchone()["n"]
        cur.execute(
            "DELETE FROM public.transform WHERE id=%(tid)s::uuid",
            dict(tid=str(transform_id)),
        )
        self._conn.commit()
        return n

    def discover_higher_dim(self, seed_node_id, k: int = 5) -> list:
        cur = self._conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT n.id, n.title, 1 - (n.embedding <=> q.embedding) AS sim
            FROM public.node n,
                 (SELECT embedding FROM public.node WHERE id=%(sid)s::uuid) q
            WHERE n.id <> %(sid)s::uuid AND n.embedding IS NOT NULL
            ORDER BY n.embedding <=> q.embedding
            LIMIT %(k)s
            """,
            dict(sid=str(seed_node_id), k=k),
        )
        return cur.fetchall()

    def clear_all(self) -> None:
        """测试用：清空所有领域表（保留 schema）。"""
        cur = self._conn.cursor(row_factory=dict_row)
        for t in ("attention_observation", "review_queue", "context_member", "context",
                  "edge", "citation", "modeling_artifact", "meta_claim",
                  "node_history", "node", "transform"):
            cur.execute(f"DELETE FROM public.{t}")
        self._conn.commit()
