# Spike 02 — 双轨分流判定（Semantic Router 路线）

> 状态：**完成（结论带限定条件）**
> 目标：验证「校准化双轨路由 + 弃权」能否把条目判为 静态 / 动态 / 不确定，并测出弃权率与错判率。

## 假设（可证伪）

1. 明确的静态/动态条目可以被语义路由正确分开（routed 准确率 ≥ 90%）。
2. 路由器**必须能弃权**（返回 None），而不是强行二选一。
3. 相似度阈值校准后，错判率可控制在 ≤10%，且弃权率落在可用区间（5%–45%）。

## 成功阈值（先于结果设定）

| 指标 | 阈值 |
|---|---|
| misroute_rate（已路由中的错判率） | ≤ 10% |
| abstain_rate | 5% – 45%（既要真能弃权，也不能怯懦到无用） |
| 模糊条目被弃权的比例 | ≥ 50% |

## 可丢弃边界

本 spike 验证**路由判定与校准/弃权逻辑**（ZKC 自研部分），编码器是可插拔的。
`router.py` 用无依赖的 TF-IDF 编码器，便于随时替换为 semantic-router + FastEmbed。

## 产出物

| 文件 | 说明 |
|---|---|
| `samples.py` | 路由定义 + 32 条留出评估集 + 12 条校准集（含 8 条真·模糊样本） |
| `router.py` | 可插拔编码器的双轨路由器：评分、校准阈值、**双信号弃权** |
| `test_routing.py` | 9 个测试（TDD 先红后绿） |
| `run_spike.py` | 校准 + 评估 + 逐条明细 + 阈值扫描 + 对抗探针 |

运行：
```bash
python3 -m unittest test_routing   # 9 passed
python3 run_spike.py
```

## 结果

```
learned: threshold=0.00  min_tokens=18
on EVAL : abstain=28.1%  misroute=0.0%  coverage=71.9%  acc_on_routed=100.0%
ambiguous: 8/8 abstained, false_commit=0
```

三项阈值**均达成**：明确条目 routed 准确率 100%，错判 0%，8 条模糊样本全部正确弃权。

## 关键发现

### 1. 相似度分数**无法**区分"模糊"与"确定"（实测）

| 信号 | 模糊均值 | 明确均值 | 是否可分 |
|---|---|---|---|
| 最高相似度 | 0.164 | 0.292 | ❌ 重叠（模糊最高 0.285 > 明确最低 0.164） |
| 决策边界（best−2nd） | 0.136 | 0.200 | ❌ 重叠 |
| **信息量（去重 token 数）** | **6.9** | **25.0** | ✅ 完全分离（模糊≤11，明确≥17） |

→ 单靠"像不像某条路由"不足以支撑弃权，必须引入第二个信号。已实现**双信号弃权**：
`弃权 = (相似度 < 阈值) OR (信息量 < 下限)`，两者都在校准集上学习。

### 2. ⚠️ 限定条件：0% 错判部分源于测试数据偏差（对抗探针已证伪）

把"长但模糊"的句子喂进去：

```
ntok=58 score=0.287 pred=dynamic  FALSE COMMIT
ntok=54 score=0.323 pred=dynamic  FALSE COMMIT
ntok=47 score=0.395 pred=dynamic  FALSE COMMIT
false commits on long-ambiguous: 3/3
```

**长度只是"短含糊"的弱代理**：一旦模糊句写长，信息量门失效，且**全部误判为 dynamic**。
→ 因此 headline 的「0% 错判 / 100% 准确率」**不可外推**到真实数据；本 spike 的评估集里模糊样本都是短句，这一点必须记账。

### 3. 系统性偏差值得警惕

所有 false commit 都指向 **dynamic**。意味着模糊条目会沉入动态轨 → 参与 decay → 变成噪声并消耗注意力。
这与"错判会污染生命周期"的判断一致，且偏差方向是单向的。

## 结论与建议

- ✅ **机制可行**：校准化路由 + 显式弃权路径可以实现，且对可区分条目效果好。
- ⚠️ **仅靠阈值校准不够**（发现 1），MVP 需要第二个弃权信号。
- ❌ **信息量/长度不是可靠信号**（发现 2），不能作为最终方案。
- **建议的下一步**：弃权信号改用
  1. **显式的"模糊"路由**（给 vague 表述配 utterance，让模糊有归属），或
  2. **决策模型**（semantic-router 的 `DecisionRouter`：单次快调用直接问"该走哪条/是否都不匹配"），
  而不是继续调阈值。
- 若采用 semantic-router，可用其 `fit()` 做概率校准并按 `confidence_threshold` 弃权（与本项目逻辑同构）。

## 真编码器复核结果（2026-10-29，已解决未决项①）

HuggingFace / FastEmbed(BGE) 在本环境被 `SSL EOF` / 超时 / 502 阻断（见环境说明），改用 ZKC MVP 栈的 **Ollama 本地嵌入** 作为真实语义编码器复核，结果与词法编码器一致：

| 编码器 | 模糊/确定相似度分离 | 长模糊误判 | routed 准确率 |
|---|---|---|---|
| TF-IDF（词法，基线） | OVERLAP | 3/3 误判为 dynamic | 100% |
| Ollama nomic-embed-text（768 维） | **OVERLAP**（模糊 max 0.894 > 明确 min 0.563） | 3/3 | 80% |
| Ollama qwen3-embedding（4096 维） | **OVERLAP**（模糊 max 0.765 > 明确 min 0.477） | 3/3 | 100% |

运行：
```bash
.venv/bin/python run_spike_ollama.py nomic-embed-text qwen3-embedding
```

**确认的三个结论（真编码器下仍成立）**：
1. 「相似度不可分模糊/确定」**不是词法编码器假象**——两个独立真实模型均 OVERLAP，双信号弃权在真编码器下仍必要。
2. 长模糊句单向误判为 dynamic **三编码器一致复现（3/3）** → 单向偏差真实存在，信息量门不可靠。
3. 「0% 错判不可外推」获佐证：nomic 下 routed 准确率降至 80%、错判 20% → EVAL 集短模糊偏差使结论偏乐观。

→ 原「词法编码器上成立」限定**撤销**，改为「真实语义编码器下同样成立」。

## 未决

- ✅（已解决）真实语义编码器下模糊/确定分布是否分开 → 见上，结论：仍 OVERLAP，双信号弃权必要。
- 静态/动态的判定是否还需要时间特征（如"本周转下周转"等时间词），而非纯语义。

## 环境说明（重要，影响本 spike 的结论强度）

| 步骤 | 结果 |
|---|---|
| `pip install semantic-router[fastembed]` | ✅ 成功（耗时 ~50 分钟）→ `semantic-router 1.1.1`、`fastembed 0.9.1` |
| `import semantic_router` | ✅ 成功 |
| FastEmbed(BGE) 经 HuggingFace 加载 | ❌ **被墙** —— `SSL EOF` / 超时 / 502，重试 40 次均失败；`run_spike_real.py` 保留作 HF 路径证据 |
| Ollama 本地嵌入（nomic-embed-text / qwen3-embedding） | ✅ **成功**（Ollama 0.33.3 已装，正是 ZKC MVP 栈）→ 真编码器复核走 `run_spike_ollama.py` |

→ 真编码器复核已通过 Ollama 完成，结论见上「真编码器复核结果」。若日后 HF 可达，亦可 `.venv/bin/python run_spike_real.py BAAI/bge-small-zh-v1.5` 复算交叉验证。

**「相似度无法区分模糊与确定」现已在真实语义编码器（Ollama nomic/qwen3）下确认成立，原「词法编码器上成立」限定撤销。**

其他：
- `python3 -m venv .venv` 在工作区创建了 `.venv`（约 280M）；后由 zj 手动移至 `spikes/spike-02-dual-track-routing/.venv`，该路径已被仓库级 `.gitignore` 的 `.venv*/` 规则排除，不会进提交。
