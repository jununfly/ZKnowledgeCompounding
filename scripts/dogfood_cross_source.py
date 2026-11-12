#!/usr/bin/env python3
"""ZKC · 跨源强制算子真实 LLM dogfood（roadmap 1-5-2 验证器）。

用途：在本机起 Ollama 后手动执行，验证生产算子 zkc.cross_source.CrossSourceOperator
的真实链路（注入 callable 直连 Ollama /v1 JSON 模式，不经 Instructor——
Instructor 正式接线属 1-5-6 后续切片）。

无 Ollama 环境执行 → 打印 SKIP 并以 0 退出（非失败）。

用法：
    python3 scripts/dogfood_cross_source.py [ollama_url] [model]

默认模型 qwen3.5:4b-mlx（实现计划 §2 蒸馏默认档；Spike 11 实证 4B 稳定 3/3）。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc.cross_source import CrossSourceOperator  # noqa: E402
from zkc.r14_telemetry import record_run  # noqa: E402

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:4b-mlx"

# 复用 Spike 10/11 语料形态：5 条互关联中文动态条目（同一项目经历的不同侧面）
SOURCES = [
    {"id": "s1-auth", "title": "鉴权返工", "content":
        "把鉴权逻辑放在客户端做，被安全评审整体打回，服务端全部重做，返工两周。"},
    {"id": "s2-sdk", "title": "SDK 升级", "content":
        "第三方 SDK 的升级一直拖到上游停止维护前一周才做，被动手忙脚乱，也是两周。"},
    {"id": "s3-bypass", "title": "临时绕过", "content":
        "评审提出的临时绕过方案最后都变成长期负担，没有任何人主动回头拆。"},
    {"id": "s4-perf", "title": "压测前置", "content":
        "把连接池压测前置到设计阶段后，上线前的瓶颈改动成本接近于零。"},
    {"id": "s5-debt", "title": "技术债记账", "content":
        "技术债必须记账并带责任人，团队坚持一个季度后大约三分之一被主动清理。"},
]
QUERY = "从这些项目经历中提炼出一个关于技术决策时机的可复用方法论"


def _chat(url: str, model: str, prompt: str) -> str:
    """Ollama 原生 /api/chat，format=json + think=false（provider seam 的最小实现）。

    两条实测铁律（spike-10 rerun.py 记录 + 本次 dogfood 复现定位）：
    1. Qwen3.5 默认按原生 256K context 加载 → 16GB 机器 residency ~15GB → 推理爬行。
       **每次调用必须显式钉死 think=false + num_ctx=8192**。
    2. **/v1 端点 + response_format {"type":"json_object"} 对 qwen3.5-mlx 永久挂死**
       （单次小调用 >900s 无响应；同请求去掉 response_format 13s 返回，
       原生 /api/chat + format:"json" 0.6s 返回）。Instructor Mode.JSON 不发
       response_format（走提示层），故 spike 未踩；真实接线（1-5-6）禁用
       Mode.JSON_SCHEMA/OPENAI_TOOLS 或直接走 /api/chat。
    JSON 合规由 prompt 约束 + 调用方正则抽取兜底（同 spike 的提示层路线）。
    """
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "format": "json",
        # num_predict 必须显式给足：默认截断会把产物 JSON 腰斩（缺 claims 等必填字段）
        "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1024},
    }).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"]


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL

    # ---- 可达性探测：不通则 SKIP（dogfood 非阻塞）
    try:
        _chat_list = urllib.request.urlopen(url + "/api/tags", timeout=3).read()
        names = [m["name"] for m in json.loads(_chat_list).get("models", [])]
        if model not in names:
            print(f"SKIP: model {model!r} not in ollama ({names})")
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"SKIP: ollama unreachable ({exc})")
        return 0

    import re

    def _json_block(raw: str) -> dict:
        """从 LLM 文本中提取第一个 JSON 对象（宽松，容忍围栏/前后缀）。"""
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError(f"no JSON object in LLM output: {raw[:120]!r}")
        return json.loads(m.group(0))

    def summarize(src: dict, query: str) -> str:
        raw = _chat(url, model,
                    f"针对问题「{query}」，只依据下面这条来源，给出一句与该问题相关的要点总结"
                    f"（不要复述全文，不超过 60 字）。只输出 JSON：{{\"point\": \"...\"}}。\n\n"
                    f"[{src['title']}]\n{src['content']}")
        return str(_json_block(raw).get("point", ""))[:120] or src["title"]

    def score(summary: str, query: str) -> float:
        raw = _chat(url, model,
                    f"问题：「{query}」。以下总结对该问题的支撑度打分 0~1。"
                    f"只输出 JSON：{{\"score\": 0.0}}。\n\n{summary}")
        return float(max(0.0, min(1.0, float(_json_block(raw).get("score", 0.0)))))

    SCHEMA_HINT = (
        '输出必须是且仅是如下结构的 JSON（字段名逐字遵守）：\n'
        '{"title": str, "kind": "methodology"|"mental_model"|"tradeoff_map",\n'
        ' "claims": [{"statement": str, "level": "principle"|"pattern"|'
        '"antipattern"|"tradeoff", "confidence": 0.0~1.0,\n'
        '            "evidence_ids": [来源 id 数组，跨源断言须 >=2 个不同 id]}],\n'
        ' "local": [str], "global": [str], "methodology_steps": [str]}\n'
    )

    def generate(prompt: str):
        from zkc.cross_source import CrossSourceArtifact
        # spike-10 非膨胀重试：每次从头重建消息，只带一条短修正提示。
        # schema 提示随 prompt 注入（等同 Instructor Mode.JSON 的提示层行为）。
        last: Exception | None = None
        for attempt in range(2):
            p = prompt + "\n\n" + SCHEMA_HINT
            if attempt and last is not None:
                p = (prompt + "\n\n" + SCHEMA_HINT +
                     f"\n上一次输出未通过结构校验（{str(last)[:60]}）。"
                     "请重新输出完整对象，字段名逐字遵守，补全所有必填字段。")
            try:
                return CrossSourceArtifact.model_validate(_json_block(_chat(url, model, p)))
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise last  # type: ignore[misc]

    op = CrossSourceOperator(summarize, score, generate)

    t0 = time.perf_counter()
    out = op.combine(QUERY, SOURCES)
    wall = time.perf_counter() - t0
    art, rep = out["artifact"], out["report"]

    print("=== dogfood cross_source (real Ollama) ===")
    print(f"model={model}  wall={wall:.1f}s")
    print(f"kept={[k['id'] for k in rep['kept']]}  dropped={[d['id'] for d in rep['dropped']]}")
    print(f"completion_fired={rep['completion_fired']}  "
          f"main={rep['main_latency_ms']:.0f}ms  "
          f"completion={rep['completion_latency_ms']}")
    print(f"n_cross_source_final={rep['n_cross_source_final']}  "
          f"min_required={rep['min_cross_source']}")
    print(f"quality={rep['quality']}")
    print(f"title={art['title']!r}  kind={art['kind']}")
    for c in art["claims"]:
        print(f"  - [{c.get('level')}] {c.get('statement')!r} <- {c.get('evidence_ids')}")

    # ---- R14 遥测落库（1-27）：真实 run 的 completion_fired/latency 追加到
    # data/r14_telemetry.jsonl，供 judge_r14 聚合裁决。不伪造数据；设环境变量
    # ZKC_NO_R14_TELEMETRY=1 可跳过落库。
    if not __import__("os").environ.get("ZKC_NO_R14_TELEMETRY"):
        # run_id 含毫秒时间戳 nonce：同语料重复 run 也作为独立真实样本入 telemetry，
        # 否则 kept_ids 恒定会触发 record_run 去重、阻塞 1-27-2 的 ≥10 样本积累。
        tel = record_run(rep, run_id=f"cross_source:{rep.get('kept_ids')}:{int(time.time()*1000)}")
        if tel.get("skipped"):
            print(f"R14 telemetry: skipped (dup run_id {tel['run_id']})")
        else:
            print(f"R14 telemetry: recorded run (file=data/r14_telemetry.jsonl)")

    gate = rep["n_cross_source_final"] >= rep["min_cross_source"]
    print(f"CROSS-SOURCE GATE: {'PASS' if gate else 'FAIL'}")
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
