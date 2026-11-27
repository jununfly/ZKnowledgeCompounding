"""Compare the nine wired unit commands against the Python process oracle.

Process-only verification helper (not production code, not a migration target):

    python3 rust/app/smoke_units.py

Build `rust/app` first. Each case is sent to `metrics-snapshot unit-<unit>`
and to `oracle.py`; stdout and exit code must match byte for byte.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "rust/app/target/debug/metrics-snapshot"
ORACLE = REPO / "rust/app/oracle.py"
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"

CASES = [
    ("transport", "decode_message", ['{"jsonrpc":"2.0","id":1,"method":"ping"}']),
    ("transport", "decode_message", ["[]"]),
    ("transport", "decode_message", ["not-json"]),
    ("transport", "encode_message", [{"jsonrpc": "2.0", "id": 1, "result": None}]),
    ("transport", "is_notification", [{"jsonrpc": "2.0", "method": "x"}]),
    (
        "transport",
        "validate_arguments",
        [
            {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}},
            {"a": "x"},
        ],
    ),
    ("transport", "error_response", [1, -32601, "Method not found", None]),
    ("context", "clean_title", ['  "Hello"  ']),
    ("context", "clean_title", ["\n\n中文标题\n"]),
    ("context", "fallback_name", [["a b c", "a b d", "中文"], 3]),
    ("expiry", "route_decision", ["not-a-uuid", [], 0.5]),
    (
        "expiry",
        "route_decision",
        ["11111111-1111-4111-8111-111111111111", [], 0.0],
    ),
    (
        "expiry",
        "route_decision",
        [
            "11111111-1111-4111-8111-111111111111",
            [
                {
                    "id": "11111111-1111-4111-8111-111111111111",
                    "decay_score": 0.8999999761581421,
                    "captured": False,
                    "conn_count": 3,
                    "self_loop_count": 0,
                    "higher_dim_count": 0,
                }
            ],
            0.2,
        ],
    ),
    ("scheduling", "extract_horizon_days", ["明天交"]),
    ("scheduling", "extract_horizon_days", [None]),
    ("scheduling", "clamp_days", [500.0]),
    ("scheduling", "classify_review", [0.85]),
    (
        "scheduling",
        "baseline_for_signals",
        ["dynamic", False, "完成任务", None, False, 1, 0, 0],
    ),
    (
        "scheduling",
        "baseline_for_signals",
        ["static", False, "x", None, False, 0, 0, 0],
    ),
    ("scheduling", "adapt_interval_math", [3.0, "too_late", False]),
    ("scheduling", "adapt_interval_math", [3.0, "on_time", True]),
    ("scheduling", "l2_target", [4.0, "none"]),
    ("scheduling", "l2_target", [None, "none"]),
    ("faithfulness", "normalize", ["中文，。；：、！？“”‘’（）【】—-文本"]),
    ("faithfulness", "normalize", ["ascii ,.;:!?'\"()- text"]),
    ("faithfulness", "ngrams", ["abc", 1]),
    ("faithfulness", "ngrams", ["中文文本", 2]),
    ("faithfulness", "lcs_length", ["abcdef", "abcf"]),
    ("faithfulness", "verbatim_rate", ["abc abc", ["abc"]]),
    (
        "faithfulness",
        "overlap",
        ["安全评审要求权限判断必须在服务端完成", ["安全评审要求权限判断必须在服务端完成"]],
    ),
    ("faithfulness", "rubric_flags", ["abc", []]),
    ("faithfulness", "rubric_flags", ["完全一样的 claim", ["完全一样的 claim"]]),
    ("faithfulness", "is_forced", [None]),
    ("faithfulness", "is_forced", ["forced_x"]),
    ("faithfulness", "is_forced", ["human_only"]),
    ("routing", "tokenize", ["İstanbul STRASSE ß"]),
    ("routing", "tokenize", ["mixed 中文, text。 and “quotes”"]),
    ("routing", "tokenize", [""]),
    ("routing", "tfidf_vector", [["b", "a", "b", "c"], {"c": 1.0, "b": 0.25, "a": 3.0}]),
    ("routing", "tfidf_vector", [["missing"], {}]),
    ("routing", "cosine", [{"a": 1.0}, {"b": 1.0}]),
    ("routing", "cosine", [{"a": 1.0, "b": 2.0}, {"b": 3.0, "a": 4.0}]),
    (
        "routing",
        "cosine",
        [
            {"alpha": 0.1, "beta": 0.2, "gamma": 0.3, "delta": 0.4},
            {"gamma": 0.5, "alpha": 0.6, "delta": 0.7, "beta": 0.8},
        ],
    ),
    ("cross-source", "count_cross_source", [[{"evidence_ids": ["s1", "s1"]}]]),
    (
        "cross-source",
        "count_cross_source",
        [[{"evidence_ids": ["s1", "s2"]}, {"evidence_ids": ["s3"]}]],
    ),
    ("cross-source", "count_cross_source", [[{"evidence_ids": ["来源甲", "来源乙"]}]]),
    (
        "cross-source",
        "enforce_citations",
        [
            {
                "title": "T",
                "kind": "methodology",
                "claims": [
                    {
                        "statement": "x",
                        "level": "pattern",
                        "confidence": 0.5,
                        "evidence_ids": ["s1", "ghost", "s2"],
                    },
                    {
                        "statement": "y",
                        "level": "pattern",
                        "confidence": 0.8,
                        "evidence_ids": ["ghost"],
                    },
                ],
                "local": [],
                "global": [],
            },
            ["s1", "s2", "s3"],
        ],
    ),
    (
        "cross-source",
        "enforce_citations",
        [{"claims": [{"evidence_ids": ["s1", "s1", "s2", "s1"]}]}, ["s2", "s1", "s2"]],
    ),
    (
        "cross-source",
        "enforce_citations",
        [{"claims": [{"evidence_ids": ["β", "a", "A", "中"]}]}, ["A", "中", "β", "a", "ghost"]],
    ),
    (
        "cross-source",
        "enforce_citations",
        [
            {
                "claims": [{"evidence_ids": ["s1"]}],
                "evidence_refs": ["old"],
                "_dropped_claims": 99,
                "title": "T",
            },
            ["s1"],
        ],
    ),
    (
        "cross-source",
        "enforce_citations",
        [{"claims": [{"evidence_ids": ["ghost"]}]}, ["s1"]],
    ),
    ("distill", "extract_json", ['prefix {"claims": [{"text": "结论"}], "x": 1} suffix']),
    ("distill", "extract_json", ['{"a": 1} trailing {"b": 2}']),
    (
        "distill",
        "parse_json_output",
        [
            '{"claims":[{"text":"结论 [[%s]]","topic":"t","citations":["%s","not-a-uuid","%s"]}]}'
            % (S2.upper(), S1.replace("-", ""), S1),
            [[S1, "material a"], [S2, "material b"]],
        ],
    ),
    ("distill", "parse_json_output", ['{"claims":[{}]}', [[S1, "a"]]]),
    (
        "distill",
        "parse_llm_output",
        ["结论 [[%s]] [[%s]] [[%s]] [[bad]]" % (S1, S1, S2), [[S1, "a"], [S2, "b"]]],
    ),
    ("distill", "parse_llm_output", ["  ", [[S1, "a"]]]),
    (
        "distill",
        "validate_result",
        [{
            "claims": [{
                "text": "c", "topic": "t",
                "citations": [{"source_node_id": S1, "snippet": "片段"}],
                "reverse_links": [S1],
            }],
            "notes": "note", "attempts": 7,
        }],
    ),
    (
        "distill",
        "validate_result",
        [{"claims": [{"text": "凭空结论", "topic": "t", "citations": [], "reverse_links": []}], "notes": "", "attempts": 1}],
    ),
    (
        "distill",
        "validate_result",
        [{"claims": [{"text": "it's fine", "topic": "t", "citations": [], "reverse_links": []}], "notes": "", "attempts": 1}],
    ),
    ("distill", "validate_result", [{"claims": [], "notes": "", "attempts": 1}]),
    # R14 judgment: 8 of the 20 recorded cases, covering all reason branches,
    # median parity, min_runs edges and the empty-input floor.
    ("r14", "judge_r14", [[], 0]),  # no_completion_fired (empty runs, min_runs 0)
    (
        "r14",
        "judge_r14",
        [
            [
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
            ],
            10,
        ],
    ),  # insufficient_data (3 < min_runs 10)
    (
        "r14",
        "judge_r14",
        [
            [
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
            ],
            2,
        ],
    ),  # trigger_rate_and_latency_exceed_budget (min_runs 2)
    (
        "r14",
        "judge_r14",
        [
            [
                {"completion_fired": True, "main_latency_ms": 50.0, "completion_latency_ms": 100.0},
            ],
            1,
        ],
    ),  # exceed on a single fired run (min_runs 1)
    (
        "r14",
        "judge_r14",
        [
            [
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 300.0},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
            ],
            10,
        ],
    ),  # trigger_rate_within_budget (0.4)
    (
        "r14",
        "judge_r14",
        [
            [
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 120.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 120.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 120.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 120.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 120.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 120.0},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
            ],
            10,
        ],
    ),  # completion_latency_within_budget (0.6 rate, 1.2x)
    (
        "r14",
        "judge_r14",
        [
            [
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 200.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 200.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 200.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 200.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 200.0},
                {"completion_fired": True, "main_latency_ms": 100.0, "completion_latency_ms": 200.0},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 100.0, "completion_latency_ms": None},
            ],
            10,
        ],
    ),  # trigger_rate_and_latency_exceed_budget (0.6 rate, 2.0x)
    (
        "r14",
        "judge_r14",
        [
            [
                {"completion_fired": True, "main_latency_ms": 80.0, "completion_latency_ms": 100.0},
                {"completion_fired": True, "main_latency_ms": 80.0, "completion_latency_ms": 200.0},
                {"completion_fired": True, "main_latency_ms": 80.0, "completion_latency_ms": 300.0},
                {"completion_fired": True, "main_latency_ms": 80.0, "completion_latency_ms": 400.0},
                {"completion_fired": False, "main_latency_ms": 80.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 80.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 80.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 80.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 80.0, "completion_latency_ms": None},
                {"completion_fired": False, "main_latency_ms": 80.0, "completion_latency_ms": None},
            ],
            10,
        ],
    ),  # trigger_rate_within_budget with even-median completion latency
]


def main() -> int:
    failures = []
    for unit, fn, args in CASES:
        raw = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
        build = subprocess.run(
            [str(APP), f"unit-{unit}", fn, raw], capture_output=True, text=True
        )
        oracle = subprocess.run(
            ["python3", str(ORACLE), unit, fn, raw], capture_output=True, text=True
        )
        matched = (
            build.stdout.strip() == oracle.stdout.strip()
            and build.returncode == oracle.returncode
        )
        print("PASS" if matched else "FAIL", unit, fn, raw[:60])
        if not matched:
            failures.append((unit, fn, build.returncode, build.stdout, oracle.returncode, oracle.stdout))
    print(f"{len(CASES) - len(failures)}/{len(CASES)} matched")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
