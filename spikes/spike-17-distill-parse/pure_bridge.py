"""Process-only public aliases for recording `zkc.distill`'s deterministic parse layer.

Scope
-----
The Rust port takes JSON scalars / string lists / string-keyed objects through
the PyO3 bridge. This adapter exposes the four deterministic functions of
`src/zkc/distill.py` that parse and semantically validate LLM output. Every
decision is delegated verbatim to the Python original; the adapter only crosses
an encoding seam the bridge cannot handle.

Alias map (encoding seam, not decision behavior)
------------------------------------------------
- `extract_json(raw)` -> `zkc.distill._extract_json(raw)`
- `parse_json_output(raw, source_texts)` -> `zkc.distill._parse_json_output(...)`
- `parse_llm_output(raw, source_texts)` -> `zkc.distill._parse_llm_output(...)`
- `validate_result(result)` -> `zkc.distill.validate_result(...)`

`_enc` does not encode `UUID` or dataclasses. `source_texts` crosses as a JSON
array of `[uuid_string, text]` pairs and is restored to `[(UUID, str), ...]`;
`DistillationResult/MetaClaim/Citation` are encoded to plain dicts on return and
decoded back for `validate_result`. UUID normalization, citation filtering,
ordering, `None` returns and error text all remain the original's decision.

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`_extract_json` uses the greedy `\\{.*\\}` DOTALL regex, so the substring runs
from the first `{` to the last `}`; non-dict JSON and parse failures yield None.

`_parse_json_output` requires a `claims` array and a non-empty `text` on each
claim; citations come from `citations[]` plus inline `[[uuid]]` markers, are
restricted to the source id set and de-duplicated by first occurrence. The
result carries both `citations` and `reverse_links` in that same order. Malformed
items or zero surviving claims are a None (parse failure), not a partial result.

`_parse_llm_output` treats the whole stripped text as one claim, with inline
markers as its only citations.

`validate_result` enforces the ZKC invariant: at least
`tuning.DISTILL_MIN_CITATIONS_PER_CLAIM` (currently 1) citations per claim;
empty claims are rejected. Error text includes Python `repr` of claim text.

Production boundary
-------------------
`distill_node`'s retry loop, prompt/schema text, `DistillationOperator`, LLM
callables, `revert_claim`/`revert_artifact` Storage effects and tuning calibration
stay in Python. This slice proves literal parse/validation behavior only; it is
not a distillation quality gate or hallucination-safety decision, and does not
turn a PLACEHOLDER threshold into a CALIBRATED value.

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from uuid import UUID

from zkc import distill as _distill


def _encode_result(result):
    if result is None:
        return None
    return {
        "claims": [
            {
                "text": claim.text,
                "topic": claim.topic,
                "citations": [
                    {"source_node_id": str(cit.source_node_id), "snippet": cit.snippet}
                    for cit in claim.citations
                ],
                "reverse_links": [str(uid) for uid in claim.reverse_links],
            }
            for claim in result.claims
        ],
        "notes": result.notes,
        "attempts": result.attempts,
    }


def _decode_result(value):
    return _distill.DistillationResult(
        claims=[
            _distill.MetaClaim(
                text=claim["text"],
                topic=claim["topic"],
                citations=[
                    _distill.Citation(UUID(cit["source_node_id"]), cit.get("snippet"))
                    for cit in claim.get("citations", [])
                ],
                reverse_links=[UUID(uid) for uid in claim.get("reverse_links", [])],
            )
            for claim in value["claims"]
        ],
        notes=value.get("notes", ""),
        attempts=value.get("attempts", 1),
    )


def _sources(pairs):
    return [(UUID(str(pair[0])), pair[1]) for pair in pairs]


def extract_json(raw):
    return _distill._extract_json(raw)


def parse_json_output(raw, source_texts):
    return _encode_result(_distill._parse_json_output(raw, _sources(source_texts)))


def parse_llm_output(raw, source_texts):
    return _encode_result(_distill._parse_llm_output(raw, _sources(source_texts)))


def validate_result(result):
    return _encode_result(_distill.validate_result(_decode_result(result)))
