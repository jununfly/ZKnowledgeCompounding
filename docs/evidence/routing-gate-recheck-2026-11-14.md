# routing gate 冷启动结论复核（2026-11-14）

> 触发：2026-11-14 23:30 只读巡检发现 `data/lexical_corpus.json` 现已存在，而此前 routing gate 收口结论基于「文件不存在 → 冷启动仍弃权」。本文是运行时证据（runtime-evidence），不引用过程态 carrier / Plan，也不把任何过程节点状态当 proof。

## 1. 复核方式（本机实跑，非推测）

```python
from zkc import routing
examples = routing.load_lexical_corpus("data/lexical_corpus.json")
router = routing.LexicalRouter().fit(examples)
(router.fitted, router.gate_source, router.gate, len(examples))
```

## 2. 读数

| 字段 | 值 | 含义 |
|---|---|---|
| n_examples | 68 | 落盘语料样本数 |
| fitted | True | 两类质心均达标（min_examples_per_class=3） |
| gate_source | `corpus-derived` | 门槛由语料分布推导，非 seed |
| gate | 0.4714 | `mean_out + 0.5 × (mean_in − mean_out)` |

## 3. 结论

- **旧结论「语料文件不存在 → 冷启动仍弃权」不再成立**：语料已存在，`LexicalRouter.fit()` 自动把 `gate_source` 从 `seed` 切为 `corpus-derived`，硬编码 0.5 恒弃权的缺口已闭合（实现见 `src/zkc/routing.py` 的 `_calibrate_gate`）。
- 口径不变：**corpus-derived ≠ CALIBRATED**。seed `ROUTING_LEXICAL_CONF_GATE = 0.5` 仍是 PLACEHOLDER，作类不可分时的保守回退；推导结果**不写回** `tuning.REGISTRY` 的 CALIBRATED。升 CALIBRATED 仍须走 `calibrate()` 门禁（连续埋点 + 饱和日）。
- 本次只观测门槛派生机制，**不测路由质量**：漏检率 / 误蒸馏率属系统外信号，仍未实测；与 spike07「复利系数度量」不相干，不互相冒充。
- 未改任何阈值常量、未写回 REGISTRY、未触发 distill。
- 这是单时刻读数：语料由 `ingest` 回灌持续变化，gate 值会随之漂移，本表不构成成文承诺。
