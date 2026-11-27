"""Process-only public aliases for recording `zkc.cross_source`'s literal layer.

Scope
-----
The Rust port takes JSON scalars / string lists / string-keyed objects through
the PyO3 bridge. This adapter exposes the two deterministic pure functions of
`src/zkc/cross_source.py` used by the compounding (combine) operator. Every
decision is delegated verbatim to the Python original; the adapter only gives
the bridge two public names and normalizes one encoding detail.

Alias map (encoding seam, not decision behavior)
------------------------------------------------
- `count_cross_source(claims)` -> `zkc.cross_source.count_cross_source(claims)`
- `enforce_citations(artifact, source_ids)` -> `zkc.cross_source.enforce_citations(artifact, set(source_ids))`

`source_ids` is a Python `set[str]` in production but a JSON array crosses the
bridge. `set(source_ids)` restores the callee's expected container; membership,
ordering of the result and error text remain the original's decision.

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`count_cross_source` counts claims whose `evidence_ids` contains at least two
**distinct** ids (`len(set(...)) >= 2`); repeated ids do not make a claim
cross-source.

`enforce_citations` keeps only ids present in the source set, drops claims whose
valid list is empty, then returns `dict(artifact, claims=kept, evidence_refs=
sorted(...), _dropped_claims=dropped)`. The top-level and per-claim key order of
the input artifact is preserved by Python's dict semantics; `evidence_refs` is
sorted by code point and de-duplicated. When no claim survives it raises
`ValueError("artifact rejected: all {total} claims lost their citations "
"(hallucinated provenance)")`; the total includes dropped claims.

Decision table under test
-------------------------
1. Duplicate evidence ids never count as cross-source, but are retained in the
   surviving claim's `evidence_ids`.
2. A claim with hallucinated refs alone is dropped; the rest of the artifact
   survives with `_dropped_claims` incremented.
3. Total citation collapse is a hard rejection (ValueError), not an empty
   artifact, including the zero-claim case.
4. `evidence_refs` is a sorted de-duplicated union of surviving valid ids,
   independent of source-set order and claim order.

Recording contract
------------------
`rust-anything record --count 0 --inputs tmp/cross-source-inputs.jsonl` freezes
targeted cases: empty/single/duplicate/distinct evidence ids, partial and total
citation collapse, pre-existing override keys, extra top-level/claim fields,
unsorted and duplicate source ids, Unicode ids, and all-collapsed ValueError
text with different totals (0/1/3).

Production boundary
-------------------
`CrossSourceOperator` (RCS funnel, tuning thresholds, bounded completion loop,
R14 latency telemetry), pydantic models, LLM callables and repository storage
stay in Python. This slice proves literal structural/numeric behavior only; it
is not a cross-source quality gate, not a hallucination safety decision, and
does not turn corpus-derived thresholds into CALIBRATED tuning values.

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from zkc import cross_source as _cross_source


def count_cross_source(claims):
    return _cross_source.count_cross_source(claims)


def enforce_citations(artifact, source_ids):
    return _cross_source.enforce_citations(artifact, set(source_ids))
