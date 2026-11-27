"""Process-only adapter for recording `zkc.expiry.route_expired` from JSON rows.

Scope
-----
`route_expired` is a deterministic decision table over a `SchedulableNode`
snapshot; its only Storage interaction is `store.load_schedulable()`. The
recorder's PyO3 JSON bridge cannot pass a real `Storage`, so this shim builds the
original dataclass and injects a one-method fake store, then calls the original
function verbatim. No decision logic is reimplemented here: the Python original
remains the sole recording oracle.

Adapter rules (seam behavior, not decision behavior)
----------------------------------------------------
- `rows` is a list of plain dicts; `id` strings become `UUID` so `_row_for` can
  compare them with the requested node id.
- Rows flagged `archived` are omitted, mirroring the real repository's
  `load_schedulable()` which excludes archived nodes.
- An empty or non-matching list exercises the "not schedulable" branch.
- A malformed `node_id` is passed to the original UUID conversion, so its
  ValueError text is recorded rather than synthesized.
- Non-dict rows are fed to `dict(row)` exactly as written; their TypeError /
  ValueError text belongs to the adapter boundary and is recorded verbatim.

Decision table under test (from the original module docstring)
--------------------------------------------------------------
1. Not routable when there is no schedulable row, the node is not dynamic, or
   the node is already archived. In this adapter "dynamic" is represented by
   presence in `rows`; the real repository performs that filter.
2. Not routable while `decay_score < ROT_THRESHOLD`. The reason string includes
   Python's `:g` formatting, so 0.8999999761581421 renders as `0.9`.
3. `captured=True` routes to ARCHIVE: value already lifted to the meta layer.
4. Connected / self-loop / higher-dim context routes to DISTILL unless the
   attention pressure reaches the defer threshold, in which case ABSTAIN.
5. An orphan with no structure signal routes to ABSTAIN, never silent drop.

Recording contract
------------------
`rust-anything record --count 5 --inputs tmp/expiry-inputs.jsonl` produced 57
cases (26 successful decisions, 31 expected adapter/UUID errors). The targeted
families are:

- missing row, wrong-id row and archived row → not routable;
- decay below/above the SIMULATION ROT threshold, the exact 0.9 boundary, the
  float32-expanded 0.8999999761581421 value, NaN and Infinity decay;
- captured evidence with and without structure signals, under high pressure;
- contextual nodes at pressure 0.79 / 0.8 / 0.81 / NaN / ±Infinity;
- self-loop-only, higher-dim-only, connection-only and orphan nodes;
- negative / zero / large decay scores and a malformed UUID.

Thresholds come from `zkc.tuning` and are currently SIMULATION (ROT 0.9,
PRESSURE_DEFER 0.8), not CALIBRATED. The Rust port must keep them as recorded
literals and must not promote them to calibrated constants.

Why the Rust port is longer than this shim
-------------------------------------------
- Python hands `Counter`/dataclass/UUID formatting to the standard library;
  Rust needs explicit value decoding, UUID canonicalization and a `:g` renderer.
- The recorded error texts are part of the oracle and must be matched exactly,
  including the adapter's `dict(...)` failures on non-dict rows.

Out of scope
------------
`apply_archive`, `enqueue_review`, `apply_distill`, `route_and_apply` and
`process_expired_dynamic_nodes` still take Storage / callable / datetime and
remain in Python under Q5=C. This slice proves the decision table only, not the
application layer that writes archive/review_queue rows.

Nothing in this shim is production code. It lives in the spike-08 research unit
because `rust-anything` only bridges files inside a known analyze unit. Deleting
it only breaks re-recording, not the application.
"""
from uuid import UUID

from zkc.expiry import route_expired
from zkc.repository.models import SchedulableNode


class _SnapshotStore:
    def __init__(self, rows):
        self._rows = rows

    def load_schedulable(self):
        return self._rows


def route_decision(node_id: str, rows: list[dict], attention_pressure: float) -> dict:
    """Call the original `route_expired` with a JSON-constructed snapshot."""
    snapshot = []
    for raw in rows:
        row = dict(raw)
        if row.get("archived"):
            continue
        if row.get("id") is not None:
            row["id"] = UUID(str(row["id"]))
        snapshot.append(SchedulableNode(**row))
    return route_expired(_SnapshotStore(snapshot), node_id, attention_pressure)
