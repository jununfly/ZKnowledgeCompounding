"""Fixed evaluation corpus for spike 10 (model quality re-test).

Hard requirement for a controlled comparison: BOTH models (the 1.5B baseline and the
new target model) must see byte-identical inputs, otherwise any quality delta is
confounded. The corpus is therefore frozen here and never generated per-run.

Design intent: the sources are ZKC-style DYNAMIC items (project notes / decision
records, Chinese), and they are deliberately inter-related so that a competent combine
operator CAN produce cross-source assertions (the exact thing spike 05 failed at:
one claim per source, no cross-source synthesis). If a model still produces
one-claim-per-source output on this corpus, that is evidence about the model,
not about the corpus.
"""
from __future__ import annotations

SOURCES = [
    {
        "id": "s1",
        "title": "A 项目：鉴权被安全评审打回",
        "content": (
            "为了赶上线，我们把鉴权校验放在了客户端，服务端只做粗粒度检查。"
            "安全评审直接打回，要求所有权限判断必须在服务端完成。"
            "返工花了两周，比当初省下的四天多得多。"
        ),
    },
    {
        "id": "s2",
        "title": "B 项目：第三方 SDK 强制升级",
        "content": (
            "第三方 SDK 宣布旧版本三个月后停服。我们一直拖到停服前一周才升级，"
            "结果发现 API 全变了，被动返工两周。"
            "教训是：外部依赖的到期时间不是我们的排期时间。"
        ),
    },
    {
        "id": "s3",
        "title": "复盘：临时绕过都会变长期负担",
        "content": (
            "复盘近三个项目，发现一个共性：所有先临时绕过后面再补的决定，"
            "最后都没有被补上，反而变成了系统的长期负担。"
            "临时方案一旦上线，就再也不会有人主动拆掉它。"
        ),
    },
    {
        "id": "s4",
        "title": "C 项目：压测前置到设计阶段",
        "content": (
            "这次我们把压测从上线前提前到了设计评审阶段，"
            "在设计阶段就发现了连接池瓶颈，改动成本几乎为零。"
            "对比以往上线前才发现，代价差了一个数量级。"
        ),
    },
    {
        "id": "s5",
        "title": "团队约定：技术债必须记账",
        "content": (
            "团队新约定：任何临时绕过都必须写进技术债台账，带责任人和预计清理时间。"
            "两个月下来，台账里有三分之一被真正清理了。"
            "剩下没清理的至少是已知的，而不是意外的。"
        ),
    },
]

# The question the combine operator must answer from the corpus above.
QUERY = "短期交付压力与长期维护成本之间，应当如何权衡？"

# Distillation uses a smaller slice (spike 04 distills from a few sources into ONE claim).
DISTILL_SOURCE_IDS = ["s1", "s3", "s5"]
