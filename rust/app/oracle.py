"""Process-only oracle for the three library-unit front doors.

This is NOT production code and NOT a migration target. It exists so the
`RUST_ANYTHING_UNIT_<UNIT>=original` kill switch has the same meaning for the
pure-function slices as it does for `metrics-snapshot`: send the request to the
Python original instead of the Rust port. Every call delegates verbatim to the
Python function the port was recorded from (context/expiry via the process-only
spike aliases). The Rust port is never consulted here.

Usage: python3 rust/app/oracle.py <unit> <fn> '<json-arguments>'
Output: {"ok": <value>} on success, {"error": "<Type>: <text>"} on failure.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def load_alias(path: Path, module_name: str):
    """Load a spike alias by path: both spikes define a file named pure_bridge.py."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTEXT_ALIAS = load_alias(
    REPO / "spikes" / "spike-06-context-assembly" / "pure_bridge.py",
    "zkc_context_pure_oracle",
)
EXPIRY_ALIAS = load_alias(
    REPO / "spikes" / "spike-08-expiry-routing" / "pure_bridge.py",
    "zkc_expiry_pure_oracle",
)

TRANSPORT = {
    "contract_snapshot": ("zkc.transport.contract", "contract_snapshot"),
    "tool_schema": ("zkc.transport.contract", "tool_schema"),
    "is_blacklisted": ("zkc.transport.contract", "is_blacklisted"),
    "is_allowlisted": ("zkc.transport.contract", "is_allowlisted"),
    "validate_arguments": ("zkc.transport.mcp_server", "validate_arguments"),
    "decode_message": ("zkc.transport.protocol", "decode_message"),
    "encode_message": ("zkc.transport.protocol", "encode_message"),
    "is_notification": ("zkc.transport.protocol", "is_notification"),
    "result_response": ("zkc.transport.protocol", "result_response"),
    "error_response": ("zkc.transport.protocol", "error_response"),
}
CONTEXT = {
    "clean_title": (CONTEXT_ALIAS, "clean_title"),
    "fallback_name": (CONTEXT_ALIAS, "fallback_name"),
}
EXPIRY = {
    "route_decision": (EXPIRY_ALIAS, "route_decision"),
}
TABLES = {
    "transport": TRANSPORT,
    "context": CONTEXT,
    "expiry": EXPIRY,
}


def main() -> int:
    unit, fn, raw = sys.argv[1:4]
    args = json.loads(raw)
    try:
        module, name = TABLES[unit][fn]
        target = (
            getattr(importlib.import_module(module), name)
            if isinstance(module, str)
            else getattr(module, name)
        )
        value = target(*args)
        print(json.dumps({"ok": value}, ensure_ascii=False, separators=(",", ":")))
    except Exception as exc:  # the original exception text is part of the oracle
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, separators=(",", ":")))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
