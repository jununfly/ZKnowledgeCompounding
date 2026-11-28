"""Process-only oracle for the fifteen library-unit front doors.

This is NOT production code and NOT a migration target. It exists so the
`RUST_ANYTHING_UNIT_<UNIT>=original` kill switch has the same meaning for the
pure-function slices as it does for `metrics-snapshot`: send the request to the
Python original instead of the Rust port. Every call delegates verbatim to the
Python function the port was recorded from (context/expiry via the process-only
spike aliases). The Rust port is never consulted here.

Usage: python3 rust/app/oracle.py <unit> <fn> '<json-arguments>'
Output: {"ok": <value>} on success, {"error": "<Type>: <text>"} on failure.

The first argument may carry the front-door `unit-` prefix (e.g.
`unit-transport`), so the same argv shape works for `rust-anything app
record --inputs` cases and the wired Rust command `metrics-snapshot
unit-transport`. The prefix is stripped before table lookup.
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
SCHEDULING_ALIAS = load_alias(
    REPO / "spikes" / "spike-09-review-interval" / "pure_bridge.py",
    "zkc_scheduling_interval_oracle",
)
FAITH_ALIAS = load_alias(
    REPO / "spikes" / "spike-10-model-quality" / "pure_bridge.py",
    "zkc_faithfulness_rubric_oracle",
)
ROUTING_ALIAS = load_alias(
    REPO / "spikes" / "spike-15-routing-tfidf" / "pure_bridge.py",
    "zkc_routing_tfidf_oracle",
)
CROSS_SOURCE_ALIAS = load_alias(
    REPO / "spikes" / "spike-16-cross-source-enforcement" / "pure_bridge.py",
    "zkc_cross_source_oracle",
)
DISTILL_ALIAS = load_alias(
    REPO / "spikes" / "spike-17-distill-parse" / "pure_bridge.py",
    "zkc_distill_oracle",
)
R14_ALIAS = load_alias(
    REPO / "spikes" / "spike-18-r14-judgment" / "pure_bridge.py",
    "zkc_r14_oracle",
)
ARTIFACT_SHAPING_ALIAS = load_alias(
    REPO / "spikes" / "spike-19-artifact-shaping" / "pure_bridge.py",
    "zkc_artifact_shaping_oracle",
)
INJECTION_ALIAS = load_alias(
    REPO / "spikes" / "spike-20-injection-detection" / "pure_bridge.py",
    "zkc_injection_oracle",
)
PERCENTILE_ALIAS = load_alias(
    REPO / "spikes" / "spike-21-percentile" / "pure_bridge.py",
    "zkc_percentile_oracle",
)
OPERATOR_GUARD_ALIAS = load_alias(
    REPO / "spikes" / "spike-22-operator-guard" / "pure_bridge.py",
    "zkc_operator_guard_oracle",
)
TELEMETRY_VALIDATION_ALIAS = load_alias(
    REPO / "spikes" / "spike-23-telemetry-validation" / "pure_bridge.py",
    "zkc_telemetry_validation_oracle",
)
SCHEDULE_RENDER_ALIAS = load_alias(
    REPO / "spikes" / "spike-24-schedule-render" / "pure_bridge.py",
    "zkc_schedule_render_oracle",
)
REVIEW_GATE_ALIAS = load_alias(
    REPO / "spikes" / "spike-27-review-gate" / "pure_bridge.py",
    "zkc_review_gate_oracle",
)
CAPTURE_PROFILE_ALIAS = load_alias(
    REPO / "spikes" / "spike-26-capture-profile" / "pure_bridge.py",
    "zkc_capture_profile_oracle",
)
MCP_EXPOSURE_ALIAS = load_alias(
    REPO / "spikes" / "spike-25-mcp-exposure" / "pure_bridge.py",
    "zkc_mcp_exposure_oracle",
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
SCHEDULING = {
    "extract_horizon_days": (SCHEDULING_ALIAS, "extract_horizon_days"),
    "clamp_days": (SCHEDULING_ALIAS, "clamp_days"),
    "baseline_for_signals": (SCHEDULING_ALIAS, "baseline_for_signals"),
    "classify_review": (SCHEDULING_ALIAS, "classify_review"),
    "adapt_interval_math": (SCHEDULING_ALIAS, "adapt_interval_math"),
    "l2_target": (SCHEDULING_ALIAS, "l2_target"),
}
FAITHFULNESS = {
    "normalize": (FAITH_ALIAS, "normalize"),
    "ngrams": (FAITH_ALIAS, "ngrams"),
    "lcs_length": (FAITH_ALIAS, "lcs_length"),
    "verbatim_rate": (FAITH_ALIAS, "verbatim_rate"),
    "overlap": (FAITH_ALIAS, "overlap"),
    "rubric_flags": (FAITH_ALIAS, "rubric_flags"),
    "is_forced": (FAITH_ALIAS, "is_forced"),
}
ROUTING = {
    "tokenize": (ROUTING_ALIAS, "tokenize"),
    "tfidf_vector": (ROUTING_ALIAS, "tfidf_vector"),
    "cosine": (ROUTING_ALIAS, "cosine"),
}
CROSS_SOURCE = {
    "count_cross_source": (CROSS_SOURCE_ALIAS, "count_cross_source"),
    "enforce_citations": (CROSS_SOURCE_ALIAS, "enforce_citations"),
}
DISTILL = {
    "extract_json": (DISTILL_ALIAS, "extract_json"),
    "parse_json_output": (DISTILL_ALIAS, "parse_json_output"),
    "parse_llm_output": (DISTILL_ALIAS, "parse_llm_output"),
    "validate_result": (DISTILL_ALIAS, "validate_result"),
}
R14 = {
    "judge_r14": (R14_ALIAS, "judge_r14"),
}
ARTIFACT_SHAPING = {
    "to_modeling_artifact": (ARTIFACT_SHAPING_ALIAS, "to_modeling_artifact"),
}
INJECTION = {
    "detect_injection_markers": (INJECTION_ALIAS, "detect_injection_markers"),
}
PERCENTILE = {
    "percentile": (PERCENTILE_ALIAS, "percentile"),
}
OPERATOR_GUARD = {
    "require_operator": (OPERATOR_GUARD_ALIAS, "require_operator"),
}
TELEMETRY_VALIDATION = {
    "validate_report": (TELEMETRY_VALIDATION_ALIAS, "validate_report"),
}
SCHEDULE_RENDER = {
    "build_task_action": (SCHEDULE_RENDER_ALIAS, "build_task_action"),
    "build_register_command": (SCHEDULE_RENDER_ALIAS, "build_register_command"),
    "build_unregister_command": (SCHEDULE_RENDER_ALIAS, "build_unregister_command"),
}
REVIEW_GATE = {
    "review_payload_gate": (REVIEW_GATE_ALIAS, "review_payload_gate"),
}
CAPTURE_PROFILE = {
    "validate_capture_profile": (CAPTURE_PROFILE_ALIAS, "validate_capture_profile"),
}
MCP_EXPOSURE = {
    "attack_surface_table": (MCP_EXPOSURE_ALIAS, "attack_surface_table"),
    "entry_names": (MCP_EXPOSURE_ALIAS, "entry_names"),
}
TABLES = {
    "transport": TRANSPORT,
    "context": CONTEXT,
    "expiry": EXPIRY,
    "scheduling": SCHEDULING,
    "faithfulness": FAITHFULNESS,
    "routing": ROUTING,
    "cross-source": CROSS_SOURCE,
    "distill": DISTILL,
    "r14": R14,
    "artifact-shaping": ARTIFACT_SHAPING,
    "injection": INJECTION,
    "percentile": PERCENTILE,
    "operator-guard": OPERATOR_GUARD,
    "telemetry-validation": TELEMETRY_VALIDATION,
    "schedule-render": SCHEDULE_RENDER,
    "review-gate": REVIEW_GATE,
    "capture-profile": CAPTURE_PROFILE,
    "mcp-exposure": MCP_EXPOSURE,
}


def main() -> int:
    unit, fn, raw = sys.argv[1:4]
    if unit.startswith("unit-"):
        unit = unit[len("unit-"):]
    args = json.loads(raw)
    try:
        module, name = TABLES[unit][fn]
        target = (
            getattr(importlib.import_module(module), name)
            if isinstance(module, str)
            else getattr(module, name)
        )
        # spike-09 keeps `human` keyword-only; the CLI sends it as the third
        # positional slot, so restore the original call shape here.
        kwargs = {}
        if unit == "scheduling" and fn == "adapt_interval_math":
            kwargs = {"human": args[2]}
            args = args[:2]
        value = target(*args, **kwargs)
        print(json.dumps({"ok": value}, ensure_ascii=False, separators=(",", ":")))
    except Exception as exc:  # the original exception text is part of the oracle
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, separators=(",", ":")))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
