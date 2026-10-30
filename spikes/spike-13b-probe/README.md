# Spike 13b-probe · judge 执行模型实证（qwen3.5:9b-mlx）

> 状态：**运行中 / 待回填**。本 probe 是 Spike 13 §1.1「关键实证 gate」的执行：
> 在 16GB 本机实测 `qwen3.5:9b-mlx`（8.9GB，已拉取）的三项指标，决定它能否作为
> Spike 13 默认的本地 7B–9B 批量 judge。

## 目标（回答 Spike 13 §1.1 的三个 gate）

| 指标 | 来源字段 | 判定含义 |
|---|---|---|
| JSON 合规率 | `empty_atomic_fallback`（空原子回退次数 / 总调用） | 模型能否产出 `parse_judgment` 可解析的结构；空原子=不合规，将强制人审（Spike 13 §3） |
| 单条延迟 | `call_time_median_s` | 能否用批量异步吸收（人从每日队列异步复审，非同步等待） |
| 危险漏检率 | `dangerous_false_negative_rate` | truth 非 supported 却判 supported 的比例——唯一决定能否 auto-pass 的指标 |

## 方法

- 复用 Spike 12 `run_spike12.py`（已加 `--model` / `--limit`，零逻辑改动）。
- judge 机制：`judge.py` 分解式判定 + `parse_judgment` 防御式解析（不用 instructor，Spike 12 §5 已证其卡死）。
- golden 集：Spike 12 的 13 例（5 supported / 5 contradicted / 3 partial）。
- 代理：脚本内已设 `NO_PROXY=localhost,127.0.0.1`（Spike 12 根因：localhost 走 WorkBuddy 代理会挂死）。

## 运行

```bash
# 快速探针（2 例 × 1 采样，确认 JSON 合规 + 延迟）
python run_spike12.py --model qwen3.5:9b-mlx --limit 2 --samples 1 \
    --out spike-13b-probe/probe_9b_quick.json

# 全量（13 例 × 3 采样）
python run_spike12.py --model qwen3.5:9b-mlx --samples 3 \
    --out spike-13b-probe/probe_9b_full.json
```

## 决策门槛（Spike 13 §1.1）

- **采纳 9b 本地批量 judge（默认）**：JSON 合规率高（少量空原子，且空原子已被强制人审兜住）
  + 延迟可批量吸收 + 危险漏检率可接受（待定阈值，初判 < 某值）。
- **降级到字面 rubric + 人工兜底**：9b 也不产 JSON 或危险漏检过高 → 走 Spike 13 §1.1 降级链第 2 级。
- 任何情况**绝不静默 auto-pass**（空原子/矛盾强制人审已在 Spike 13 §3 写死）。

## 结果（回填区）

实测于 16GB Mac（本机），`qwen3.5:9b-mlx` 已拉取（8.9GB）。

**单条探针（example g6, truth=contradicted, 受控单调用 timeout=600）**
- model: `qwen3.5:9b-mlx`
- 单条延迟: **364.5s（≈6 分钟）**
- JSON 合规: **FAIL** — 模型不吐 JSON，吐结构化自然语言（`Label: contradicted` / `Evidence: [s1]` / `Overall: contradicted`），`parse_judgment` 报 `no-json-block-in-output`
- 判定质量: **正确** — 准确识别 g6 矛盾（claim「客户端」vs 来源「服务端」→ contradicted），引用正确来源 `[s1]`
- 原始输出见 `probe_9b_raw.txt`

**Ollama 服务端日志交叉印证（同次运行）**
- `/v1/chat/completions` 单次耗时：`4m11s`、`5m0s`（触发 500 超时 context canceled）、`2m47s`
- 内存峰值 ~9.1 GiB held ~8.5–9.0 GiB；运行期系统空闲内存仅 ~90MB → **疑似内存压力拖慢 decode**（~0.4 tok/s）

**全量评测**: 未跑（单条已 6min 且非 JSON；13 例 ×3 采样 ≈ 39 调用 ≈ 数小时且大量超时，无信息增量）。

### 结论（回答 §1.1 三个 gate）

| gate | 9B 结果 | 判定 |
|---|---|---|
| JSON 合规 | 非 JSON（结构化文本，parser 无法解析） | ❌ |
| 单条延迟 | ~6min/条（decode ~0.4 tok/s，疑似内存压力） | ❌ 批量也不可吸收 |
| 危险漏检率 | 未测（先被延迟/格式否决） | — |

**本地 7B–9B instruct 在 16GB 本机被实证否决** → 触发 Spike 13 §1.1 降级链 **第 2 级**：
**字面 rubric 预过滤（Spike 10/11 verbatim/overlap/citation_hit，快且可自动化） + 人工兜底剩余**。

**关键定性（避免误读）**：
- 9B（及此前 4B）**判定能力本身成立**（g6 矛盾被正确识别、引用正确来源），失败在 **decode 速度 + 非 JSON 格式**，非算法/能力缺陷。
- 格式问题可修（写 `Label:/Evidence:/Overall:` 的定制 parser，或强制 TOOLS/JSON 模式）；但 **速度属硬件绑定**，本机 16GB 不解决则无解。
- 一旦换更快硬件 / 离盒 / 云端 opt-in，判定器（`judge.py` + `run_spike12.py` 零改动）即可启用——能力已验证。
- **MVP 忠实度闸门 = human-in-the-loop（Spike 13 §3/§4）+ 字面 rubric 预过滤**；自动 LLM 预过滤层在本机暂时缺席，直至更快 judge 就位。

### 下一步
1. 更新 Spike 13 §1.1：本地 7B–9B 标为「本机实证否决」，MVP 走 rubric+人工。
2. （可选）若未来有更快机器：先用定制 parser 验证 9B 能否出合规结构，再跑 `run_spike12.py` 拿真实危险漏检率。
3. 评估云端 judge opt-in 的隐私/离线权衡（仅显式选择）。
