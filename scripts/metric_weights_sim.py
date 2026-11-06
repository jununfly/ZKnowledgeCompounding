#!/usr/bin/env python
"""ZKC · spike07 复利度量权重 / method_target 的受控仿真（SIMULATION 依据，可复跑）。

只读：读一次真实存储度量快照；**不写业务库、不写 tuning.REGISTRY**。
产出 ``docs/evidence/metric-weights-simulation.{json,md}``。

这份证据只支撑 ``source=SIMULATION``，即「给既有占位值补上可复核的设计依据」：
- 权重是「什么是好的复利」的**价值判断**，不是可从无标注数据估计的统计量；
- 无外生偏好时，均匀先验下 Bayes 最优预测权重 = 先验均值 = 等权 0.25×4（解析可证 + 仿真复验）；
- 真实快照中三个分量恒 0，权重在其上**完全不可辨识**，故绝不改值、更不得标 CALIBRATED。

升 ``CALIBRATED`` 仍需 ``tuning.can_calibrate`` 门禁（≥14 天埋点 + ≥3 饱和日）
与 zj 显式给出的外生价值排序（四分量偏好），本脚本一律不代填。

用法：
    python scripts/metric_weights_sim.py                     # 默认读真实 PG（只读）
    python scripts/metric_weights_sim.py --storage memory    # 无 PG 环境复跑
    python scripts/metric_weights_sim.py --samples 20000 --seed 20261106
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from zkc import tuning  # noqa: E402
from zkc.repository import get_storage  # noqa: E402
from zkc import metrics as M  # noqa: E402

SEED = 20261106
SAMPLES = 20000
TARGET_CANDIDATES = (5.0, 8.0, 10.0, 14.0, 20.0, 50.0)
MO_GRID_MAX = 20  # 覆盖「14 天窗口 × 1.0/天预算」可达产出并留出余量

EQUAL = (0.25, 0.25, 0.25, 0.25)
SKEW = (0.40, 0.30, 0.20, 0.10)


# ---------------------------------------------------------------- 纯函数层

def dirichlet_uniform(rng: random.Random, k: int = 4) -> tuple[float, ...]:
    """Dirichlet(1,...,1)：k 个 Exp(1) 归一化，即单纯形上的均匀分布。"""
    draws = [-math.log(1.0 - rng.random()) for _ in range(k)]
    total = sum(draws)
    return tuple(d / total for d in draws)


def cf(x: tuple[float, ...], w: tuple[float, ...]) -> float:
    """复利系数 = 四项归一分量按权重线性合成（与 metrics.compounding_factor 同式）。"""
    return sum(a * b for a, b in zip(x, w))


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def _pearson(a: list[float], b: list[float]) -> float:
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a)
    db = sum((y - mb) ** 2 for y in b)
    return num / math.sqrt(da * db) if da and db else 0.0


def candidate_weights(rng: random.Random) -> dict[str, tuple[float, ...]]:
    out: dict[str, tuple[float, ...]] = {"equal": EQUAL, "skew": SKEW}
    for i, name in enumerate(("density", "reuse", "method", "decay")):
        out[f"heavy_{name}"] = tuple(0.7 if j == i else 0.1 for j in range(4))
    for i in range(2):
        out[f"random_{i + 1}"] = dirichlet_uniform(rng)
    return out


def simulate_weights(samples: int, seed: int) -> dict:
    """均匀先验下，比较各候选权重相对「真权重」的均方误差。

    解析结论：若 w_true ~ Dirichlet(1,1,1,1) 且与场景 x 独立，
    E[(w_true·x - c·x)^2] = Var(w_true·x) + ((E[w_true] - c)·x)^2，
    在单纯形上唯一最小化点是 c = E[w_true] = (0.25,...)。本仿真只做数值复验。
    """
    rng = random.Random(seed)
    cands = candidate_weights(random.Random(seed + 1))
    sq = {name: 0.0 for name in cands}
    true_vals: list[float] = []
    equal_vals: list[float] = []

    for _ in range(samples):
        x = tuple(rng.random() for _ in range(4))  # 合成场景，非真实行为
        w_true = dirichlet_uniform(rng)
        target = cf(x, w_true)
        true_vals.append(target)
        equal_vals.append(cf(x, EQUAL))
        for name, w in cands.items():
            sq[name] += (target - cf(x, w)) ** 2

    mse = {name: round(v / samples, 6) for name, v in sq.items()}
    best = min(mse, key=mse.get)
    return {
        "samples": samples,
        "seed": seed,
        "scene_distribution": "x_i ~ Uniform[0,1] iid，四维独立；合成场景，非真实埋点",
        "true_weight_prior": "Dirichlet(1,1,1,1) = 单纯形均匀先验（表示无任何外生偏好信息）",
        "analytic_optimum": list(EQUAL),
        "analytic_argument": (
            "E[(w_true·x - c·x)^2] = Var(w_true·x) + ((E[w_true]-c)·x)^2；"
            "E[w_true]=(0.25,0.25,0.25,0.25)，故 c=等权 唯一最小化期望平方误差"
        ),
        "candidates": {name: list(w) for name, w in cands.items()},
        "mse": mse,
        "excess_risk_vs_equal": {
            name: round((v - mse["equal"]) / mse["equal"], 4)
            for name, v in mse.items() if name != "equal"
        },
        "best": best,
        "equal_is_best": best == "equal",
        "spearman_equal_vs_true": round(_pearson(_ranks(true_vals), _ranks(equal_vals)), 4),
    }


def identifiability(real: dict) -> dict:
    """真实快照上的权重可辨识性：CF 对每个权重的敏感度 = 对应分量值。"""
    target = tuning.get("METRIC_METHOD_TARGET")
    x_real = (
        real["connection_density"], real["reuse_rate"],
        min(1.0, real["methodology_output"] / target) if target else 0.0,
        real["decay_controllability"],
    )
    names = ("METRIC_W_DENSITY", "METRIC_W_REUSE", "METRIC_W_METHOD", "METRIC_W_DECAY")
    sensitivity = {n: round(v, 4) for n, v in zip(names, x_real)}
    nonzero = [n for n, v in zip(names, x_real) if v > 0.0]
    return {
        "x_real_normalized": [round(v, 4) for v in x_real],
        "sensitivity_dCF_dw": sensitivity,
        "identifiable_weights": nonzero,
        "unidentifiable_weights": [n for n in names if n not in nonzero],
        "nonzero_component_count": len(nonzero),
        "conclusion": (
            "CF(w) = Σ w_i·x_i；真实快照中只有 "
            f"{len(nonzero)} 个非零分量，仅 {', '.join(nonzero)} 可辨识，"
            "任意重分配其余三个权重都不改变 CF。"
            "真实数据对「权重校准」零信息量，因此不得据真实快照改权重值，"
            "更不得把任何权重标为 calibrated。"
        ),
    }


def target_analysis(real: dict) -> dict:
    """method_target 的饱和/区分度分析 + 观察窗口产能推导（设计依据，非真实行为）。"""
    window_days = tuning.get("CALIB_MIN_DAYS")
    budget_per_day = tuning.get("BUDGET_PER_DAY_DEFAULT")
    ceiling = window_days * budget_per_day  # 转化率 ≤1 的乐观上界
    current = tuning.get("METRIC_METHOD_TARGET")
    mo_values = list(range(MO_GRID_MAX + 1))
    rows = []
    for t in TARGET_CANDIDATES:
        norms = [min(1.0, mo / t) for mo in mo_values]
        rows.append({
            "target": t,
            "mean_norm": round(statistics.fmean(norms), 4),
            "std_norm": round(statistics.pstdev(norms), 4),
            "saturated_ratio_on_grid": round(sum(mo >= t for mo in mo_values) / len(mo_values), 4),
            "distinct_levels": len({round(n, 4) for n in norms}),
            "unsaturated_ratio_in_reachable_window": round(
                sum(mo < t for mo in range(int(ceiling) + 1)) / (int(ceiling) + 1), 4),
        })
    real_norm = {str(t): round(min(1.0, real["methodology_output"] / t), 4)
                 for t in TARGET_CANDIDATES}
    return {
        "mo_grid": f"0..{MO_GRID_MAX} 的整数产出（合成网格，非真实埋点）",
        "window_days": window_days,
        "budget_per_day": budget_per_day,
        "reachable_output_ceiling": ceiling,
        "ceiling_rationale": (
            "观察窗口 = CALIB_MIN_DAYS；默认注意力预算 = BUDGET_PER_DAY_DEFAULT；"
            "每次处理最多凝结 1 条方法论产物 → 可达产出上界 = 窗口 × 预算。"
            "这是设计量级推导，不是真实产出分布"
        ),
        "current_target": current,
        "current_vs_ceiling": round(current / ceiling, 4),
        "candidates": rows,
        "real_mo_norm_by_target": real_norm,
        "all_targets_equivalent_on_real": len(set(real_norm.values())) == 1,
        "conclusion": (
            f"target={current} 约为窗口可达上界 {ceiling:g} 的 {current / ceiling:.0%}，"
            "在可达区间内保留不饱和梯度；但真实 methodology_output="
            f"{real['methodology_output']} 使所有候选 target 的 mo_norm 完全相同，"
            "故 target 在真实数据上不可辨识，保留原值、仅升 SIMULATION。"
        ),
    }


def pg_composition() -> dict:
    """PG 后端的只读构成核查：确认 dc=1.0 来自「归档」而非蒸馏/结合引用。

    只有真实库才能回答「CF 是不是复利产物撑起来的」；metrics_report 的四个数字
    只是推断，这里给出直接证据。失败如实记录 error，不静默略过。
    """
    from zkc.repository.connection import connect

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT count(*) FILTER (WHERE track='dynamic'),
                   count(*) FILTER (WHERE track='dynamic' AND archived_at IS NOT NULL),
                   count(*) FILTER (WHERE track='dynamic' AND decay_score >= 0.9),
                   count(*) FILTER (WHERE track='dynamic' AND decay_score >= 0.9
                                    AND archived_at IS NOT NULL),
                   count(*) FILTER (WHERE track='dynamic' AND decay_score >= 0.9
                                    AND archived_at IS NULL)
            FROM node
        """)
        dyn, dyn_archived, expired, expired_archived, expired_active = cur.fetchone()
        counts = {}
        for table in ("meta_claim", "citation", "modeling_artifact", "edge"):
            cur.execute(f"SELECT count(*) FROM {table}")
            counts[table] = cur.fetchone()[0]
        cur.execute("SELECT id FROM node WHERE track='dynamic' AND decay_score >= %s",
                    (tuning.get("ROT_THRESHOLD"),))
        expired_ids = {row[0] for row in cur.fetchall()}
        refs: set = set()
        for table in ("meta_claim", "modeling_artifact"):
            cur.execute(f"SELECT evidence_refs FROM {table}")
            for (arr,) in cur.fetchall():
                refs.update(arr or [])
        return {
            "dynamic_nodes": dyn,
            "dynamic_archived": dyn_archived,
            "expired_dynamic": expired,
            "expired_and_archived": expired_archived,
            "expired_active": expired_active,
            "table_counts": counts,
            "expired_referenced_by_claims_or_artifacts": len(expired_ids & refs),
            "conclusion": (
                "到期动态节点全部来自已归档分支，且全库无任何 claim/citation/artifact/edge；"
                "decay_controllability=1.0 不含蒸馏或结合引用，CF=0.25 不代表复利健康度。"
                if expired == expired_archived and expired_active == 0
                and counts["meta_claim"] == 0 and counts["modeling_artifact"] == 0
                else "构成与预期不同，需人工复核，不得据此下结论"
            ),
        }
    except Exception as exc:  # 只读核查失败也要如实留痕
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        conn.close()


def load_real_snapshot(storage_kind: str) -> dict:
    """只读：走生产 metrics_report，与 /metrics 面板同一口径。"""
    return M.metrics_report(get_storage(storage_kind))


def build_result(storage_kind: str, samples: int, seed: int) -> dict:
    real = load_real_snapshot(storage_kind)
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "purpose": "spike07 复利度量 METRIC_W_* / METRIC_METHOD_TARGET 的 SIMULATION 依据",
        "storage": storage_kind,
        "real_snapshot": real,
        "pg_composition": pg_composition() if storage_kind == "pg" else None,
        "weight_simulation": simulate_weights(samples, seed),
        "real_snapshot_identifiability": identifiability(real),
        "method_target_analysis": target_analysis(real),
        "scope_limits": [
            "合成场景（Uniform 分量 + Dirichlet 真权重）是受控仿真，不是真实用户行为或埋点；"
            "因此结论只能支撑 source=SIMULATION。",
            "本脚本只读：不写业务库、不写 tuning.REGISTRY、不调用 calibrate()。",
            "source=CALIBRATED 另需 ≥14 天埋点 + ≥3 饱和日门禁，以及 zj 对四分量价值的"
            "显式外生排序与真实复用/连接密度/方法论产出分布；本脚本一律不代填。",
            "E8 锚2 的蒸馏质量度量（漏检率/误蒸馏率）是系统外抽检信号，"
            "与 spike07 系统自算的复利系数是两套度量，不得互相冒充证据。",
            "真实快照中 cd/rr/mo 三项恒 0、CF 由归档型 decay_controllability 单独撑起；"
            "此时合成值 CF 不代表复利健康度，复盘必须同时看四个分量。",
        ],
    }


def _composition_lines(r: dict) -> list[str]:
    comp = r.get("pg_composition")
    if comp is None:
        return ["### 1.1 真实库构成复核（仅 PG 后端可用）", "",
                "- 本次为 memory 后端，跳过构成核查。", ""]
    if "error" in comp:
        return ["### 1.1 真实库构成复核（只读 SQL）", "",
                f"- 核查失败（如实留痕）：{comp['error']}", ""]
    rows = [
        ("动态节点 / 其中已归档", f"{comp['dynamic_nodes']} / {comp['dynamic_archived']}"),
        ("到期动态 / 其中已归档 / 活跃到期",
         f"{comp['expired_dynamic']} / {comp['expired_and_archived']} / {comp['expired_active']}"),
        ("meta_claim / citation / modeling_artifact / edge",
         " / ".join(str(comp["table_counts"][k]) for k in
                    ("meta_claim", "citation", "modeling_artifact", "edge"))),
        ("到期节点被 claim / artifact evidence_refs 引用数",
         str(comp["expired_referenced_by_claims_or_artifacts"])),
    ]
    out = ["### 1.1 真实库构成复核（只读 SQL）", "",
           "| 项 | 值 |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in rows]
    out += ["", f"- 结论：{comp['conclusion']}", ""]
    return out


def render_markdown(r: dict, storage_kind: str, samples: int, seed: int) -> str:
    real = r["real_snapshot"]
    ws = r["weight_simulation"]
    ident = r["real_snapshot_identifiability"]
    ta = r["method_target_analysis"]
    lines = [
        "# spike07 复利度量权重 / method_target 受控仿真（SIMULATION 依据）",
        "",
        f"- 采集时刻：{r['as_of']}",
        f"- 命令：`python scripts/metric_weights_sim.py --storage {storage_kind} "
        f"--samples {samples} --seed {seed}`",
        f"- 真实快照来源：`zkc.metrics.metrics_report` 只读查询（后端 `{storage_kind}`），与 `/metrics` 面板同口径。",
        "- 脚本只读：不写业务库、不写 `tuning.REGISTRY`、不调用 `calibrate()`。",
        "",
        "## 1. 真实快照（外生锚现状）",
        "",
        "| connection_density | reuse_rate | citations_per_claim | methodology_output | decay_controllability | compounding_factor |",
        "|---|---|---|---|---|---|",
        "| " + " | ".join(str(real[k]) for k in (
            "connection_density", "reuse_rate", "citations_per_claim",
            "methodology_output", "decay_controllability", "compounding_factor")) + " |",
        "",
        *_composition_lines(r),
        f"归一化分量 x = {ident['x_real_normalized']}；非零分量数 = "
        f"{ident['nonzero_component_count']}（仅 {', '.join(ident['identifiable_weights'])} 可辨识）。"
        f" 当前 CF={real['compounding_factor']} 完全由归档型 decay_controllability 撑起："
        "该分量在本次快照中来自「到期节点已归档」（见 "
        "`docs/evidence/d2-corpus-cleanup-2026-11-05.md`，24 条归档后 due 归零），"
        "不是蒸馏/结合的复利产物。"
        "**四分量结构性为 0 时，合成值 CF 不可当作复利健康度解读，必须同时看分量。**",
        "",
        "### 权重可辨识性（∂CF/∂w_i = x_i）",
        "",
        "| 权重 | 敏感度 |",
        "|---|---|",
    ]
    lines += [f"| `{n}` | {v} |" for n, v in ident["sensitivity_dCF_dw"].items()]
    lines += [
        "",
        f"结论：{ident['conclusion']}",
        "",
        "## 2. 等权 0.25 的依据（均匀先验下 Bayes 最优）",
        "",
        f"- 真权重先验：{ws['true_weight_prior']}；场景：{ws['scene_distribution']}。",
        f"- 解析：{ws['analytic_argument']}。",
        f"- 样本数 {ws['samples']}；等权与「真权重」CF 的 Spearman 秩相关 = "
        f"{ws['spearman_equal_vs_true']}（点估计 MSE 最优 ≠ 单场景排序完全一致；"
        "该量级说明未知偏好下单个场景的排名仍有分歧，更不该用偏权去「猜」偏好）。",
        "",
        "| 候选权重 | 均方误差 MSE | 相对等权的超额风险 |",
        "|---|---|---|",
    ]
    for name, v in sorted(ws["mse"].items(), key=lambda kv: kv[1]):
        extra = ws["excess_risk_vs_equal"].get(name)
        lines.append(f"| `{name}` | {v} | " + ("—" if extra is None else f"+{extra:.0%}") + " |")
    lines += [
        "",
        f"最小 MSE 候选 = `{ws['best']}`；等权是否为最优 = **{ws['equal_is_best']}**。"
        " 任何偏离等权的取值都等于注入一组未经外生验证的价值偏好。",
        "",
        "## 3. method_target 的饱和 / 区分度",
        "",
        f"- 可达量级推导：观察窗口 {ta['window_days']} 天 × 默认注意力预算 "
        f"{ta['budget_per_day']}/天 → 产出上界 {ta['reachable_output_ceiling']:g}"
        f"（{ta['ceiling_rationale']}）。",
        f"- {ta['conclusion']}",
        "",
        "| target | mo_norm 均值 | 标准差 | 网格饱和率 | 可分辨层级数 | 可达窗口内不饱和率 |",
        "|---|---|---|---|---|---|",
    ]
    for row in ta["candidates"]:
        lines.append(
            f"| {row['target']:g} | {row['mean_norm']} | {row['std_norm']} | "
            f"{row['saturated_ratio_on_grid']} | {row['distinct_levels']} | "
            f"{row['unsaturated_ratio_in_reachable_window']} |"
        )
    lines += [
        "",
        "## 4. 口径限制（诚实声明）",
        "",
    ]
    lines += [f"- {s}" for s in r["scope_limits"]]
    lines += [
        "",
        "**本次结论只把 `METRIC_W_*` / `METRIC_METHOD_TARGET` 从 `PLACEHOLDER` 升为 "
        "`SIMULATION`，数值一律不变；这不等于「已按真实行为校准」。**",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="复利度量权重受控仿真（SIMULATION 依据）")
    ap.add_argument("--storage", default="pg", choices=("pg", "memory"),
                    help="真实快照后端；无 PG 环境用 memory 复跑（快照会退化为空库）")
    ap.add_argument("--samples", type=int, default=SAMPLES)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out-dir", default=str(_HERE.parent / "docs" / "evidence"))
    args = ap.parse_args(argv)

    r = build_result(args.storage, args.samples, args.seed)
    if not r["weight_simulation"]["equal_is_best"]:
        print("E_SIMULATION_INVARIANT: 等权不再是均匀先验下最小 MSE 候选，"
              "证据不成立，拒绝写出", file=sys.stderr)
        return 2

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "metric-weights-simulation.json"
    md_path = out / "metric-weights-simulation.md"
    json_path.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(r, args.storage, args.samples, args.seed),
                       encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"real snapshot: {r['real_snapshot']}")
    print(f"best weight candidate: {r['weight_simulation']['best']} "
          f"(equal_is_best={r['weight_simulation']['equal_is_best']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
