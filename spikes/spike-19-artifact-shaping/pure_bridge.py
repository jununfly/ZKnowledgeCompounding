"""Process-only public alias for recording `zkc.cross_source.to_modeling_artifact`.

Scope
-----
The Rust port takes a JSON-native artifact dict plus an optional produced_by
UUID string through the PyO3 bridge. This adapter exposes the single pure
dict -> ModelingArtifact shaping function. Every decision is delegated verbatim
to the Python original; the adapter only crosses the encoding seams PyO3 cannot
handle.

Alias map (encoding seam, not decision behavior)
------------------------------------------------
- `to_modeling_artifact(artifact, produced_by)` ->
    `zkc.cross_source.to_modeling_artifact(artifact, produced_by=produced_by)`
  * `produced_by` is keyword-only in Python; the alias exposes it as a plain
    second positional argument and restores the keyword when delegating
    (same pattern as spike-09's `human=` and spike-18's `min_runs=`).
  * the returned `ModelingArtifact` is a plain dataclass with UUID / datetime
    fields that PyO3 `_enc` cannot encode (it would fall back to `$repr`); the
    alias encodes it to a field-fixed dict with UUID -> str and datetime ->
    isoformat. Key filtering, UUID conversion of evidence_refs and all field
    defaults stay the original's.

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`to_modeling_artifact` takes title/kind from the artifact dict (default ""),
keeps the full dict as body minus underscore-prefixed internal keys and the
promoted `evidence_refs` column, converts evidence_refs str -> UUID and carries
produced_by for provenance. Invalid UUID text raises ValueError in the original
(the exception text is recorded verbatim as a literal, never promoted).

Production boundary
-------------------
This slice proves literal shaping behavior only. It does not run
`CrossSourceOperator.combine` (RCS funnel + citation enforcement + completion),
does not write Storage, and does not emit R14 telemetry. `apply_combine` /
`revert_artifact` stay in Python. Nothing here is production code: deleting the
alias only breaks re-recording and the kill switch, not the Rust port.

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from uuid import UUID

from zkc import cross_source as _cross_source


def _uuid_str(value):
    return str(value) if value is not None else None


def _encode_artifact(ma):
    return {
        "id": _uuid_str(ma.id),
        "title": ma.title,
        "kind": ma.kind,
        "body": ma.body,
        "evidence_refs": [str(e) for e in ma.evidence_refs],
        "produced_by": _uuid_str(ma.produced_by),
        "revises": _uuid_str(ma.revises),
        "created_at": ma.created_at.isoformat() if ma.created_at is not None else None,
    }


def to_modeling_artifact(artifact, produced_by):
    return _encode_artifact(
        _cross_source.to_modeling_artifact(artifact, produced_by=produced_by)
    )
