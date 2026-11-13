# spike07 复利度量权重 / method_target 受控仿真（SIMULATION 依据）

> ⚠️ **本文件为 2026-11-06 受控仿真快照（source=SIMULATION），非当前生效依据。**
> 权重 / method_target 已于 2026-11-11 经人工覆盖标定为 `CALIBRATED`（数值维持等权结论），当前生效值见 `src/zkc/tuning.py` 的 `CALIB_OVERRIDE_AT` 常量。本快照仅作「等权选择」的推导佐证，不得当作现行参数。

- 采集时刻：2026-11-06T08:17:09.321808+00:00
- 命令：`python scripts/metric_weights_sim.py --storage pg --samples 20000 --seed 20261106`
- 真实快照来源：`zkc.metrics.metrics_report` 只读查询（后端 `pg`），与 `/metrics` 面板同口径。
- 脚本只读：不写业务库、不写 `tuning.REGISTRY`、不调用 `calibrate()`。

## 1. 真实快照（外生锚现状）

| connection_density | reuse_rate | citations_per_claim | methodology_output | decay_controllability | compounding_factor |
|---|---|---|---|---|---|
| 0.0 | 0.0 | 0.0 | 0 | 1.0 | 0.25 |

### 1.1 真实库构成复核（只读 SQL）

| 项 | 值 |
|---|---|
| 动态节点 / 其中已归档 | 61 / 24 |
| 到期动态 / 其中已归档 / 活跃到期 | 24 / 24 / 0 |
| meta_claim / citation / modeling_artifact / edge | 0 / 0 / 0 / 0 |
| 到期节点被 claim / artifact evidence_refs 引用数 | 0 |

- 结论：到期动态节点全部来自已归档分支，且全库无任何 claim/citation/artifact/edge；decay_controllability=1.0 不含蒸馏或结合引用，CF=0.25 不代表复利健康度。

归一化分量 x = [0.0, 0.0, 0.0, 1.0]；非零分量数 = 1（仅 METRIC_W_DECAY 可辨识）。 当前 CF=0.25 完全由归档型 decay_controllability 撑起：该分量在本次快照中来自「到期节点已归档」（见 `docs/evidence/d2-corpus-cleanup-2026-11-05.md`，24 条归档后 due 归零），不是蒸馏/结合的复利产物。**四分量结构性为 0 时，合成值 CF 不可当作复利健康度解读，必须同时看分量。**

### 权重可辨识性（∂CF/∂w_i = x_i）

| 权重 | 敏感度 |
|---|---|
| `METRIC_W_DENSITY` | 0.0 |
| `METRIC_W_REUSE` | 0.0 |
| `METRIC_W_METHOD` | 0.0 |
| `METRIC_W_DECAY` | 1.0 |

结论：CF(w) = Σ w_i·x_i；真实快照中只有 1 个非零分量，仅 METRIC_W_DECAY 可辨识，任意重分配其余三个权重都不改变 CF。真实数据对「权重校准」零信息量，因此不得据真实快照改权重值，更不得把任何权重标为 calibrated。

## 2. 等权 0.25 的依据（均匀先验下 Bayes 最优）

- 真权重先验：Dirichlet(1,1,1,1) = 单纯形均匀先验（表示无任何外生偏好信息）；场景：x_i ~ Uniform[0,1] iid，四维独立；合成场景，非真实埋点。
- 解析：E[(w_true·x - c·x)^2] = Var(w_true·x) + ((E[w_true]-c)·x)^2；E[w_true]=(0.25,0.25,0.25,0.25)，故 c=等权 唯一最小化期望平方误差。
- 样本数 20000；等权与「真权重」CF 的 Spearman 秩相关 = 0.777（点估计 MSE 最优 ≠ 单场景排序完全一致；该量级说明未知偏好下单个场景的排名仍有分歧，更不该用偏权去「猜」偏好）。

| 候选权重 | 均方误差 MSE | 相对等权的超额风险 |
|---|---|---|
| `equal` | 0.012601 | — |
| `skew` | 0.016719 | +33% |
| `random_1` | 0.023063 | +83% |
| `random_2` | 0.027931 | +122% |
| `heavy_reuse` | 0.034423 | +173% |
| `heavy_method` | 0.035131 | +179% |
| `heavy_decay` | 0.035234 | +180% |
| `heavy_density` | 0.035335 | +180% |

最小 MSE 候选 = `equal`；等权是否为最优 = **True**。 任何偏离等权的取值都等于注入一组未经外生验证的价值偏好。

## 3. method_target 的饱和 / 区分度

- 可达量级推导：观察窗口 14 天 × 默认注意力预算 1.0/天 → 产出上界 14（观察窗口 = CALIB_MIN_DAYS；默认注意力预算 = BUDGET_PER_DAY_DEFAULT；每次处理最多凝结 1 条方法论产物 → 可达产出上界 = 窗口 × 预算。这是设计量级推导，不是真实产出分布）。
- target=10.0 约为窗口可达上界 14 的 71%，在可达区间内保留不饱和梯度；但真实 methodology_output=0 使所有候选 target 的 mo_norm 完全相同，故 target 在真实数据上不可辨识，保留原值、仅升 SIMULATION。

| target | mo_norm 均值 | 标准差 | 网格饱和率 | 可分辨层级数 | 可达窗口内不饱和率 |
|---|---|---|---|---|---|
| 5 | 0.8571 | 0.2904 | 0.7619 | 6 | 0.3333 |
| 8 | 0.7857 | 0.3254 | 0.619 | 9 | 0.5333 |
| 10 | 0.7381 | 0.3387 | 0.5238 | 11 | 0.6667 |
| 14 | 0.6429 | 0.345 | 0.3333 | 15 | 0.9333 |
| 20 | 0.5 | 0.3028 | 0.0476 | 21 | 1.0 |
| 50 | 0.2 | 0.1211 | 0.0 | 21 | 1.0 |

## 4. 口径限制（诚实声明）

- 合成场景（Uniform 分量 + Dirichlet 真权重）是受控仿真，不是真实用户行为或埋点；因此结论只能支撑 source=SIMULATION。
- 本脚本只读：不写业务库、不写 tuning.REGISTRY、不调用 calibrate()。
- source=CALIBRATED 另需 ≥14 天埋点 + ≥3 饱和日门禁，以及 zj 对四分量价值的显式外生排序与真实复用/连接密度/方法论产出分布；本脚本一律不代填。
- E8 锚2 的蒸馏质量度量（漏检率/误蒸馏率）是系统外抽检信号，与 spike07 系统自算的复利系数是两套度量，不得互相冒充证据。
- 真实快照中 cd/rr/mo 三项恒 0、CF 由归档型 decay_controllability 单独撑起；此时合成值 CF 不代表复利健康度，复盘必须同时看四个分量。

**本次结论只把 `METRIC_W_*` / `METRIC_METHOD_TARGET` 从 `PLACEHOLDER` 升为 `SIMULATION`，数值一律不变；这不等于「已按真实行为校准」。**
