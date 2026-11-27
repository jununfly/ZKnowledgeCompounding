"""Compare the three wired unit commands against the Python process oracle.

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
