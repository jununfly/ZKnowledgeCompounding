"""ZKC 阈值常量表（P1.4 · 唯一权威来源）。

背景（zj 拍板 2026-10-31，实施计划 §2「阈值治理」）：
全仓原本**没有**集中的常量文件——`ROT_THRESHOLD = 0.9` 在 5 处重复定义
（spike-01/decay_model.py:14、spike-08/store.py:21、spike-07/metrics.py:15、
spike-07/store.py:17、spike-09/interval_policy.py:32），`budget_per_day = 1.2`
甚至不是常量、只是硬编码且无出处。改一处漏四处是真实风险。

本模块是**新代码（zkc/）的唯一阈值来源**。旧 spike 目录保持原样——它们是
「时间胶囊」式的验证证据，历史结论必须可复现，不回改。

三条铁律：
1. 每个参数都带 `source` 标签，禁止裸数字出现在业务代码里。
2. `source` 从 `placeholder`/`simulation` 升到 `calibrated` 必须过门禁
   （`can_calibrate`），不得手改。
3. 改值必须留痕：旧值 → 新值 + 触发条件 + 日期（见 `Parameter.history`）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ---------------------------------------------------------------- 来源标签

PLACEHOLDER = "placeholder"   # 无数据支撑，占位（ZKC 是新系统，开工前标定不了）
SIMULATION = "simulation"      # 仿真/受控实验得出的结论（带限定，非真实行为）
CALIBRATED = "calibrated"      # 真实埋点数据校准过（须过 can_calibrate 门禁）
_SOURCES = (PLACEHOLDER, SIMULATION, CALIBRATED)


@dataclass
class Parameter:
    name: str
    value: Any
    source: str
    note: str = ""
    calibrated_at: date | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.source not in _SOURCES:
            raise ValueError(f"{self.name}: source 必须是 {_SOURCES} 之一，收到 {self.source!r}")
        if self.source == CALIBRATED and self.calibrated_at is None:
            raise ValueError(f"{self.name}: source=calibrated 必须带 calibrated_at")

    def set(self, value: Any, source: str, when: date, reason: str) -> None:
        """改值必须留痕（旧值→新值 + 触发条件 + 日期）。"""
        if source not in _SOURCES:
            raise ValueError(f"source 必须是 {_SOURCES} 之一，收到 {source!r}")
        self.history.append(
            {
                "from": self.value,
                "to": value,
                "from_source": self.source,
                "to_source": source,
                "at": when.isoformat(),
                "reason": reason,
            }
        )
        self.value = value
        self.source = source
        self.calibrated_at = when if source == CALIBRATED else None


# ---------------------------------------------------------------- 常量表

SPIKE14_AT = date(2026, 10, 31)   # spike 14 实测日期：编码器与维度在此定死


def _p(name: str, value: Any, source: str, note: str = "",
       calibrated_at: date | None = None) -> Parameter:
    return Parameter(name=name, value=value, source=source, note=note,
                     calibrated_at=calibrated_at)


REGISTRY: dict[str, Parameter] = {
    # ---- 衰减（spike 01：线性当选；阶梯否决；指数备选）
    p.name: p
    for p in [
        _p("DECAY_FUNCTION", "linear", SIMULATION,
           "spike 01：阶梯否决（表面与腐化阈值同瞬跨越、行动窗口 0、rot 100%）；"
           "指数窗口大但触发过晚"),
        _p("SURFACE_THRESHOLD", 0.6, SIMULATION,
           "进入注意力的 decay 点；有效复审节奏 = SURFACE × interval"),
        _p("ROT_THRESHOLD", 0.9, SIMULATION,
           "已腐化点。**原在 5 处重复定义，本表是唯一来源**"),
        # ---- review_interval L1 个体基线（spike 09）
        _p("BASELINE_CAPTURED_DAYS", 28, PLACEHOLDER,
           "已捕获条目（单程票）：拉长观察 28d → 到期即 ARCHIVE，永不回 DISTILL（ADR-0002）"),
        _p("BASELINE_SELF_LOOP_DAYS", 3, PLACEHOLDER,
           "L1 顺序中 self_loop 压过已捕获：项目躬身入局的条目即便被提炼过，原件仍在变"),
        _p("BASELINE_CONNECTED_DAYS", 14, PLACEHOLDER, "有 edge 或 higher_dim"),
        _p("BASELINE_ORPHAN_DAYS", 7, PLACEHOLDER, "孤儿条目"),
        _p("MIN_INTERVAL_DAYS", 1.0, SIMULATION, "interval 钳制下界"),
        _p("MAX_INTERVAL_DAYS", 180.0, SIMULATION, "interval 钳制上界"),
        # ---- L2 预算归一化（spike 09 切片 B）
        _p("BUDGET_PER_DAY_DEFAULT", 1.0, PLACEHOLDER,
           "原 1.2 无出处，弃。1.0 偏保守：略高于真实意愿→积压→产生饱和日→估计器有样本可下调"),
        _p("OVERSUBSCRIBE_FACTOR", 1.5, SIMULATION,
           "校准期超订；否则供给=预算时队列天天清空，低估被永久固化"),
        _p("EMA_ALPHA", 0.3, SIMULATION, "budget 估计阻尼系数"),
        _p("EMA_CLAMP", 0.3, SIMULATION, "单次调整幅度 ±30%"),
        _p("PRESSURE_DEFER", 0.8, SIMULATION, "注意力压力延后阈值"),
        # ---- L3 AIMD 反馈
        _p("EARLY_THRESHOLD", 0.3, PLACEHOLDER,
           "复审时 decay < 此值 = too_early（节奏比真实腐化快，骚扰过度 → 拉长）"),
        _p("AIMD_UP", 1.5, PLACEHOLDER, "复审判 late → 缩短 interval（乘）"),
        _p("AIMD_DOWN", 0.7, PLACEHOLDER, "复审判 early → 拉长 interval（乘）"),
        _p("ON_TIME_BAND", 0.20, SIMULATION,
           "仿真判据：收敛目标 H/0.6（非真值 H），振荡带 ±50%"),
        # ---- 标注率闸门（L3 停机条件）
        _p("LABEL_RATE_MIN", 0.70, PLACEHOLDER, "滚动 7 天 labeled_completed/completed"),
        _p("LABEL_MIN_SAMPLES", 10, PLACEHOLDER,
           "窗口内 <10 次完成复审不判定（样本不足放行，避免 warm-up 冻死）"),
        _p("LABEL_WINDOW_DAYS", 7, PLACEHOLDER, "滚动窗口天数"),
        # ---- 校准门禁
        _p("CALIB_MIN_DAYS", 14, PLACEHOLDER, "连续埋点天数下限"),
        _p("CALIB_MIN_SATURATED_DAYS", 3, PLACEHOLDER, "饱和日下限"),
        # ---- 蒸馏 HITL（独立预算，不占复审预算）
        _p("F_CAP_RATIO", 0.20, PLACEHOLDER,
           "蒸馏人审封顶比例；只对蒸馏人审侧生效（R11：两套独立预算）"),
        # ---- 蒸馏语义不变式（P3.1 · 候选不提供，ZKC 自建）
        _p("DISTILL_MIN_CITATIONS_PER_CLAIM", 1, PLACEHOLDER,
           "每条 meta-claim 至少引用 1 个来源（去繁非凭空）。属逻辑不变式而非可调阈值，"
           "但经 tuning 统一出口，便于后续若放宽（如纯综述节点允许 0）可留痕"),
        # ---- embedding（spike 14 实测定死）
        _p("EMBEDDING_MODEL", "nomic-embed-text:latest", CALIBRATED,
           "spike 14 实测；仅限检索召回/反向连接候选，**严禁用于安全判定**（spike 03 实测 "
           "nomic 在相似度阈值判定下 dangerous=3），该职责归 DecisionRouter",
           calibrated_at=SPIKE14_AT,
           ),
        _p("EMBEDDING_DIM", 768, CALIBRATED,
           "spike 14 实测 768d（9.5ms/条、274MB）vs qwen3 4096d（183.2ms/条、4.7GB）。"
           "**换维度 = 重建索引**，如需升级走加列路径而非改本值",
           calibrated_at=SPIKE14_AT,
           ),
        # ---- 双轨分流（P2.2 · DecisionRouter + 词法三路双信号弃权）
        _p("ROUTING_LLM_CONF_GATE", 0.5, SIMULATION,
           "DecisionRouter(LLM) 置信度门槛；低于此强置 vague。源自 spike-03 GATE=0.5"),
        _p("ROUTING_LEXICAL_CONF_GATE", 0.5, PLACEHOLDER,
           "词法 TF-IDF 三路置信度门槛的**冷启动 seed**（PLACEHOLDER：无真实埋点支撑）。"
           "**实际运行门槛由 LexicalRouter.fit() 从拟合语料分布自动推导**（类内/类间质心余弦相似度"
           "中点），推导结果记为 gate_source='corpus-derived'——这是「语料分布推导」、与 tuning 的 "
           "CALIBRATED（运行时埋点校准）是两回事、不互相替代；corpus-derived 绝不写回本 REGISTRY 的 "
           "CALIBRATED。本 seed 仅作未 fit / 类不可分时的回退保守门槛。"
           "**第二信号严禁用 embedding**(R16：embedding 仅限检索召回/反向连接候选，"
           "spike-03 实测 nomic dangerous=3)，故用 embedding-free 词法路由作交叉验证"),
        _p("ROUTING_LEXICAL_CALIB_MIDPOINT", 0.5, PLACEHOLDER,
           "词法门槛自动推导的中点份额：gate = mean_out + 0.5*(mean_in - mean_out)。"
           "0.5=类内/类间相似度正中；越接近 0 越保守(贴近类间、少误提交)。"
           "**这是「语料分布推导」的设计默认，非运行时埋点校准**：升 CALIBRATED 须经 calibrate() "
           "门禁（≥14 天埋点 + ≥3 饱和日），仅凭语料分布推导不得越门禁"),
        _p("ROUTING_REQUIRE_DUAL_SIGNAL", True, PLACEHOLDER,
           "True=必须 LLM 与词法双信号一致才自动提交真实轨道；否则(含词法无法判定)→vague→人工。"
           "冷启动词法无训练数据时一切走人工(安全欠覆盖，非危险)，随人工定轨积累逐渐自动化"),
        # ---- P5.2 复利度量面板（spike-07 口径，权重/目标待校准）
        _p("METRIC_W_DENSITY", 0.25, PLACEHOLDER, "复利系数·连接密度权重（默认等权 0.25）"),
        _p("METRIC_W_REUSE", 0.25, PLACEHOLDER, "复利系数·复用率权重（默认等权 0.25）"),
        _p("METRIC_W_METHOD", 0.25, PLACEHOLDER, "复利系数·方法论产出权重（默认等权 0.25）"),
        _p("METRIC_W_DECAY", 0.25, PLACEHOLDER, "复利系数·衰减可控权重（默认等权 0.25）"),
        _p("METRIC_METHOD_TARGET", 10.0, PLACEHOLDER,
           "方法论产出归一化目标：达到该产出数即记满分 1.0（待真实数据校准）"),
    ]
}


# ---------------------------------------------------------------- 访问 API

def get(name: str) -> Any:
    """取参数值。业务代码一律走这里，禁止裸数字。"""
    try:
        return REGISTRY[name].value
    except KeyError:
        raise KeyError(f"未知阈值 {name!r}；请在 zkc/tuning.py 登记后再用") from None


def param(name: str) -> Parameter:
    return REGISTRY[name]


def can_calibrate(*, days_with_observation: int, saturated_days: int) -> bool:
    """校准门禁：只有真实埋点足够，才允许把 source 升为 calibrated。

    防止「无数据支撑改数」——ZKC 是新系统、无历史数据，开工前标定不了。
    """
    return (
        days_with_observation >= get("CALIB_MIN_DAYS")
        and saturated_days >= get("CALIB_MIN_SATURATED_DAYS")
    )


def calibrate(name: str, value: Any, when: date, reason: str,
              *, days_with_observation: int, saturated_days: int) -> Parameter:
    """过门禁才能置 calibrated；不过门禁直接拒绝（绝不静默放行）。"""
    if not can_calibrate(days_with_observation=days_with_observation,
                         saturated_days=saturated_days):
        raise PermissionError(
            f"{name}: 校准门禁未过 —— 需连续 ≥{get('CALIB_MIN_DAYS')} 天埋点且 "
            f"≥{get('CALIB_MIN_SATURATED_DAYS')} 个饱和日；"
            f"当前 {days_with_observation} 天 / {saturated_days} 饱和日"
        )
    p = param(name)
    p.set(value, CALIBRATED, when, reason)
    return p


def as_rows() -> list[dict[str, Any]]:
    """给 UI/日志用：显示值时必须同时显示来源标签（禁止只报数字）。"""
    return [
        {
            "name": p.name,
            "value": p.value,
            "source": p.source,
            "calibrated_at": p.calibrated_at.isoformat() if p.calibrated_at else None,
            "note": p.note,
        }
        for p in REGISTRY.values()
    ]
