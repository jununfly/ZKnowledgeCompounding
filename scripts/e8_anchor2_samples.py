#!/usr/bin/env python3
"""ZKC · 经验证伪闸锚 2 的人工抽检样本生成器（只读，不写业务库）。

来源权威：`docs/rec-avoid-gate.md` §4 与 `docs/prds/knowledge-compounding-prd.md` §9。
锚 2 要求由 zj 本人人工抽检蒸馏产物，记录漏检/误蒸馏率并给本机 4B/9B 上界估计。
本脚本只提供**可判输入**：固定中文语料 → 真实 Ollama 两臂蒸馏 → 产物快照。

边界（硬）：
  - 只调 `zkc.distill.distill_node`，**不调用** `apply_distill`，不写 node / claim /
    llm_call_score / attention_observation / review_queue，不写任何业务表；
  - **不产生 verdict、不算漏检率/误蒸馏率、不写上界结论**，全部留给 zj 填写；
  - 模型调用失败 / 超时如实写入 error 字段，绝不补造 claim。

用法：
    python3 scripts/e8_anchor2_samples.py [--models m1,m2] [--groups A,B,C]
                                          [--timeout 120] [--output <json>] [--md <kit.md>]

依赖：本机 Ollama（原生 /api/chat，铁律由 zkc.llm 内置）+ 仓库源码，无第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zkc import distill as D  # noqa: E402
from zkc.llm import DEFAULT_DISTILL_MODEL, make_distill_llm, ollama_reachable  # noqa: E402

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODELS = ["qwen3.5:4b-mlx", "qwen3.5:9b-mlx"]
DEFAULT_JSON = ROOT / "docs/evidence/e8-anchor2-samples.json"
DEFAULT_MD = ROOT / "docs/evidence/e8-anchor2-sampling-kit.md"

SYSTEM_PROMPT = (
    "将以下项目经历材料蒸馏为 1-3 条去繁后的元认知方法论结论；"
    "每条结论必须在 citations 数组中引用支撑它的来源节点 uuid。"
)

# 固定语料：组 A 与既有 dogfood 语料逐字一致；B/C 为同形态补充，便于覆盖不同失败模式。
# 这里只放**原始材料**，刻意不写「应提炼的关键点」——gold set 必须由 zj 独立给出。
CORPUS = {
    "A": [
        ("鉴权返工", "把鉴权逻辑放在客户端做，被安全评审整体打回，服务端全部重做，返工两周。"),
        ("临时绕过", "评审提出的临时绕过方案最后都变成长期负担，没有任何人主动回头拆。"),
        ("压测前置", "把连接池压测前置到设计阶段后，上线前的瓶颈改动成本接近于零。"),
    ],
    "B": [
        ("缓存击穿", "促销开始瞬间缓存集体失效，请求直接压到数据库，限流来不及生效，最后靠提前预热兜住。"),
        ("灰度回滚", "灰度批次发现转化率异常，因发布没有一键回滚，只能重跑全量流水线，多花了四十分钟。"),
        ("告警疲劳", "告警阈值照抄默认值，一周三百条里几乎全是噪声，真正那次磁盘写满被淹在里面没人看见。"),
    ],
    "C": [
        ("模型选型", "先用小模型跑通链路再换大模型，接口契约没变，替换成本只有一次回归。"),
        ("迁移分批", "一次性迁移全量表导致锁表两小时；改按租户分批后，每批可回滚，峰值锁等待降到秒级。"),
        ("文档腐化", "架构决策只写在会议纪要里，三个月后没人能对上代码，补文档时只能靠翻提交记录反推。"),
    ],
}

NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://zkc.local/e8/anchor2")


def source_id(group: str, index: int) -> str:
    return str(uuid.uuid5(NAMESPACE, "%s:%d" % (group, index)))


def model_tag(model: str) -> str:
    return model.replace(":", "-").replace("/", "-")


def run_one(group: str, model: str, url: str, timeout: float) -> dict:
    texts = [(uuid.UUID(source_id(group, i)), "%s：%s" % (title, body))
             for i, (title, body) in enumerate(CORPUS[group])]
    node_id = uuid.uuid5(NAMESPACE, "target:%s" % group)
    record = {
        "group": group,
        "model": model,
        "wall_s": None,
        "attempts": 0,
        "claims": [],
        "error": None,
    }
    t0 = time.perf_counter()
    try:
        llm = make_distill_llm(url, model, timeout=timeout)
        result = D.distill_node(node_id, texts, llm, system_prompt=SYSTEM_PROMPT)
        record["wall_s"] = round(time.perf_counter() - t0, 2)
        record["attempts"] = int(result.attempts)
        for n, claim in enumerate(result.claims, 1):
            record["claims"].append({
                "id": "%s-%s-%d" % (group, model_tag(model), n),
                "topic": claim.topic,
                "text": claim.text,
                "citations": [str(c.source_node_id) for c in claim.citations],
                "reverse_links": [str(u) for u in claim.reverse_links],
            })
    except Exception as exc:  # 模型超时 / 解析重试耗尽 / 网络错误，一律如实留痕
        record["wall_s"] = round(time.perf_counter() - t0, 2)
        record["error"] = "%s: %s" % (type(exc).__name__, exc)
    return record


def build_json(url: str, models: list, groups: list, timeout: float) -> dict:
    return {
        "schema_version": "zkc-e8-anchor2-samples/v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ollama_url": url,
        "per_call_timeout_s": timeout,
        "purpose": "rec-avoid 经验证伪闸锚 2 的人工抽检输入；verdict 与比率不由本脚本产生",
        "authority": [
            "docs/rec-avoid-gate.md §4（经验证伪闸 / 锚 2 / DoD）",
            "docs/prds/knowledge-compounding-prd.md §9（护城河实证化 P0 验收）",
        ],
        "hard_boundaries": [
            "只调 distill_node，未调 apply_distill；未写 node/claim/score/attention_observation/review_queue",
            "未生成 gold set、verdict、漏检率、误蒸馏率或 4B/9B 上界结论",
            "模型失败或超时如实记 error，不补造 claim",
        ],
        "corpus": {
            g: [{"index": i, "source_id": source_id(g, i), "title": t, "text": b}
                for i, (t, b) in enumerate(items)]
            for g, items in CORPUS.items() if g in groups
        },
        "runs": [],
    }


def render_md(data: dict) -> str:
    lines = [
        "# 锚 2 人工抽检包：蒸馏产物（待 zj 判定）",
        "",
        "- 生成时间：`%s`；Ollama：`%s`；单次调用超时：`%s`s" % (
            data["generated_at"], data["ollama_url"], data["per_call_timeout_s"]),
        "- 机器可读样本：`docs/evidence/e8-anchor2-samples.json`（同批生成，以 JSON 为准）。",
        "- 权威来源：`docs/rec-avoid-gate.md` §4、`docs/prds/knowledge-compounding-prd.md` §9。",
        "- **本文件所有判定栏与比率栏均为空白**：由 zj 本人填写，Agent 不得代填、不得代算结论。",
        "",
        "## 0. 边界（先读）",
        "",
        "1. 脚本只跑 `zkc.distill.distill_node`，未调 `apply_distill`，未写任何业务表；产物是模型输出快照，不是已入库 claim。",
        "2. 源材料只有原始文本，**刻意不提供「应提炼的关键点」**——gold set 必须由 zj 先独立写出，再看下面的产物，避免锚定偏倚。",
        "3. 漏检率 / 误蒸馏率 / 4B·9B 上界估计全部留空。",
        "",
        "## 1. 指标定义（口径先于数字）",
        "",
        "- **判定单位**：单条产出 claim（精确侧）或单条 zj 写出的应提炼关键点（召回侧）。",
        "- **漏检率（召回侧）** = `gold 中未被任何产出 claim 覆盖的关键点数 / gold 关键点总数`。"
        "覆盖 = 语义覆盖该关键点，不要求字面相同；一条 claim 可覆盖多个关键点。",
        "- **误蒸馏率（精确侧）** = `判为不合格的产出 claim 数 / 产出 claim 总数`。"
        "不合格分四类：`无据`（源文本支撑不了的编造）、`纯复述`（未升维成元认知，只是抄原文）、"
        "`错源`（citations 指向不支撑它的源节点）、`错配`（topic 与 claim 不符）。",
        "- **4B / 9B 上界估计**：两臂分别算上述两率后，由 zj 给出「本机可用模型下蒸馏质量可达的最好水平」"
        "（含是否需要更强模型 / 是否维持 HITL 的结论）。这是结论，不是脚本能算的数。",
        "- 两率分母不同，**不得合并成一个「准确率」**；样本量小，结论须带样本数。",
        "",
        "## 2. 源材料（读这一节时不要先看第 3 节）",
        "",
    ]
    for group, items in sorted(data["corpus"].items()):
        lines.append("### 组 %s" % group)
        lines.append("")
        for item in items:
            lines.append("- `%s` **%s**：%s" % (
                item["source_id"][:8], item["title"], item["text"]))
        lines.append("")
    lines += [
        "## 3. 蒸馏产物（模型输出快照）",
        "",
        "| claim id | 组 | 模型 | topic | 产物文本 | citations(前8位) | 耗时/重试 |",
        "|---|---|---|---|---|---|---|",
    ]
    for run in data["runs"]:
        meta = "%s s / %s" % (run["wall_s"], run["attempts"])
        if run["error"]:
            lines.append("| — | %s | %s | — | **调用失败**：%s | — | %s |" % (
                run["group"], run["model"], run["error"].replace("|", "/"), meta))
            continue
        if not run["claims"]:
            lines.append("| — | %s | %s | — | （无 claim） | — | %s |" % (
                run["group"], run["model"], meta))
        for claim in run["claims"]:
            cites = ", ".join(c[:8] for c in claim["citations"]) or "—"
            lines.append("| `%s` | %s | %s | %s | %s | %s | %s |" % (
                claim["id"], run["group"], run["model"],
                claim["topic"].replace("|", "/"),
                claim["text"].replace("|", "/").replace("\n", " "),
                cites, meta))
    lines += [
        "",
        "## 4. zj 判定表 · gold set（召回侧，先填）",
        "",
        "独立阅读第 2 节后写出「这段材料里应被升维成元认知结论的关键点」，再翻第 3 节填覆盖列。",
        "",
        "| 组 | 关键点 id | 应提炼的关键点（zj 写） | 是否被覆盖 | 覆盖它的 claim id |",
        "|---|---|---|---|---|",
        "| A | A-g1 |  |  |  |",
        "| A | A-g2 |  |  |  |",
        "| B | B-g1 |  |  |  |",
        "| B | B-g2 |  |  |  |",
        "| C | C-g1 |  |  |  |",
        "| C | C-g2 |  |  |  |",
        "",
        "> 行数不够自行追加；不要删减已写行。",
        "",
        "## 5. zj 判定表 · 产出 claim（精确侧）",
        "",
        "| claim id | 判定（合格/无据/纯复述/错源/错配） | 理由 |",
        "|---|---|---|",
    ]
    for run in data["runs"]:
        for claim in run["claims"]:
            lines.append("| `%s` |  |  |" % claim["id"])
    lines += [
        "",
        "## 6. 汇总（zj 填，或授权后由判定表机械汇总）",
        "",
        "| 指标 | 4B | 9B |",
        "|---|---|---|",
        "| gold 关键点数 |  |  |",
        "| 未覆盖关键点数 |  |  |",
        "| **漏检率** |  |  |",
        "| 产出 claim 数 |  |  |",
        "| 不合格 claim 数 |  |  |",
        "| **误蒸馏率** |  |  |",
        "",
        "**本机 4B / 9B 上界估计（zj 结论）**：",
        "",
        "> （留空，待 zj 填写；含是否需要更强模型、是否维持 HITL 全量人审）",
        "",
        "**抽检人 / 日期**：",
        "",
        "> （留空，待 zj 填写）",
        "",
        "## 7. 回填去向（达成后才做）",
        "",
        "抽检结果出来后，按 `docs/rec-avoid-gate.md` §4 的 DoD 回填：架构 §9 复利度量最终口径、"
        "该度量进经验证伪闸、以及 PRD §9 的护城河验收记录。**本文件本身不是达成证据**。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--groups", default="A,B,C")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--output", default=str(DEFAULT_JSON))
    ap.add_argument("--md", default=str(DEFAULT_MD))
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    groups = [g.strip().upper() for g in args.groups.split(",") if g.strip()]
    unknown = [g for g in groups if g not in CORPUS]
    if unknown:
        print("ERROR: unknown groups %s" % unknown)
        return 1
    if not ollama_reachable(args.url):
        print("SKIP: ollama unreachable (%s)" % args.url)
        return 0

    data = build_json(args.url, models, groups, args.timeout)
    for group in groups:
        for model in models:
            record = run_one(group, model, args.url, args.timeout)
            data["runs"].append(record)
            status = "error=%s" % record["error"] if record["error"] else \
                     "claims=%d" % len(record["claims"])
            print("[%s %s] %.1fs %s" % (group, model, record["wall_s"] or 0, status),
                  flush=True)

    out_json = Path(args.output)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    out_md = Path(args.md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_md(data), encoding="utf-8")
    print("written: %s" % out_json)
    print("written: %s" % out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
