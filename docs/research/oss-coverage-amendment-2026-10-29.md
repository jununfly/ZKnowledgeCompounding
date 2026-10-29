# 结论修订说明（2026-10-29）

> 修订对象：`docs/research/oss-coverage-2026-10-28-draft.md`
> （2026-10-28 开源候选覆盖调研，reportHash `50924a7c4f9306d1315575c75e626afc6396d76a6338227a607b2a25d6ce102c`）
> 修订起因：双时态（bitemporal）与双轨（dual-track）的概念辨析
> 状态：**本说明是权威增量**；原报告为 sealed artifact，不可手改，保留作对照。

---

## 1. 为什么修订

原报告在生命周期维度上，把 Utopia 的 **bitemporal（valid time + transaction time）** 记为该 topic 的 `native` 覆盖。

经验证：**bitemporal ≠ 双轨**。

- **bitemporal** 是时态数据建模机制，解决「静态型事实的演进与溯源」——回答"这个事实何时为真、我们何时知道、后来怎么改的"。
- **ZKC 的双轨**是信息类型 + 生命周期分类，核心语义是**衰减率与注意力成本**——回答"这条还有用吗、会不会腐化、还值不值得占注意力"。

二者只在「静态型信息未来可更新」这一点上重叠；**动态型信息的腐化与注意力稀缺，bitemporal 完全不覆盖**——而这正是 ZKC 的核心差异化。因此原矩阵在生命周期维度存在概念混用，需对相关评分降级。

---

## 2. 三处降级

| 项 | 原判定 | 修订后 | 原因 |
|---|---|---|---|
| Utopia · T1.2 生命周期 | `native` | **仅"时态/版本" `native`；"衰减" `absent`** | 双时态不含衰减语义；衰减在 5 个候选中全部 `absent` |
| Utopia · T3.1 蒸馏 | `native`（人审蒸馏） | 降为 `adapted` | 其 review queue 是**抽取正确性审查**（实体合并 / 事实确认），**不等于** ZKC 的"去繁 → 蒸馏到元认知" |
| OpenWiki · T3.1 蒸馏 | `native` | 降为 `adapted`（claim 结构仍 `native`） | 其"蒸馏"是 **wiki / 文档合成**，不等于 ZKC 的"元认知 + topic 组织 + 反向连接"；真正对齐的是 **Grounded Claims / OKF 的 claim 结构** |

---

## 3. 仍然成立的部分

- **Utopia**：最强的**双时态 fact schema**（correction closes old + append-only decision ledger）、**人审回路**、**air-gapped 离线**。
  且其本身为 **Rust + Postgres + pgvector**，与已选定的 substrate 同构，**模式可直接迁移**——这一点因存储报告的结论反而**加强**。
- **OpenWiki**：**Grounded Claims / OKF** 是 ZKC 元认知 claim 层最贴近的现成结构，加蒸馏流水线与 `stale_after` / `verified` 调和机制。
- **两者互补**：Utopia 供「事实演进 + 人审」，OpenWiki 供「claim 结构 + 蒸馏流水线」。
- **总结论不变**：无整体替代方案，unit-capability 复用优先；双轨建模 T0.1 与稀缺注意力调度 T5.x 无人覆盖，需自建。

---

## 4. 重述后的建议

原表述「对最对齐的两者（Utopia + OpenWiki）做 hands-on spike 验证适配度」**应重述为**：

1. **研究（非采纳）** Utopia 的双时态 schema + 人审回路 → **迁移**到自有的 Postgres schema；
2. **研究** OpenWiki 的 Grounded Claims / OKF → 用作元认知 claim 层的结构；
3. **真正的 spike 重点转向自建部分**：双轨 schema + decay 分数 + 注意力调度。

理由：存储/生命周期深挖已把 substrate 定为 **Postgres + pgvector**（自建双时态 + decay），因此**不再需要把 Utopia 当候选验证适配度**，只需把它当**模式源**。

> 关键边界：Utopia + OpenWiki 只是**子系统模式源**，不是"最接近 ZKC 的产品"，且**均不覆盖 ZKC 的差异化**（双轨 / 衰减 / 注意力）。

---

## 5. 影响范围

- 原覆盖调研报告（hash `50924a7c…`）**保留为 sealed 对照，不作手改**。
- 本说明为权威增量；如需把修订并入正式报告，可用**同一 sealed ledger 重跑**（选项 B），产出新 hash。
- 存储/生命周期深挖报告（hash `0e8de561…`）**不受影响**：它已把「生命周期/衰减建模」与「生命周期衰减(TTL)」拆成两行分别建模，结论（Postgres + pgvector + 自建双时态与衰减）仍然成立。
- 项目记忆已同步术语约定（双轨 ≠ 双时态，禁止互换）与本次修订。
