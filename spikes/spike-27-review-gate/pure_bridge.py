"""Process-only public alias for recording `zkc.review.decide_review`'s Human-only payload gate.

Scope
-----
`review_payload_gate(outcome: str, content: str|null, stale_branch: str|null) -> bool`

It constructs a fresh in-memory storage, saves one node, and calls the REAL
`zkc.review.decide_review` so the original's gate logic runs verbatim:

- valid combination  -> decide_review proceeds (and the wrapper returns `True`);
- gate violation     -> the original raises `ValueError` (recorded as a throw) before/at dispatch.

The gate is the ADR-0011/0012 HITL contract (content / stale-branch must be Human-supplied,
never auto-filled, never default-purged). The decision itself stays in the Python original — this
slice exposes only the JSON-native scalar gate (outcome/content/stale_branch), not the
Storage-bound orchestration.

Why only this slice from `decide_review`
----------------------------------------
`decide_review` / `review_queue_view` / `record_daily_observation_auto` are otherwise Storage-bound
orchestration: they read `store.nodes` / `store.attention`, perform OCC version writes, archive,
and accumulate attention observations, and `now` defaults to `datetime.now`. That is the same
dataclass/Storage encoding seam Q5 left in Python (the metrics_snapshot boundary) — porting it
standalone would be lossy and un-credible. `build_routers` likewise returns router objects + reads
env/file, not a JSON-in/JSON-out function. So this slice covers only the self-contained
Human-only payload gate.

Nothing here is production code; the security/HITL enforcement stays in Python. The recorded
messages are the HITL contract, not a new policy source.
"""
from datetime import datetime, timezone

from zkc.repository import get_storage
from zkc.repository.models import Node
from zkc.review import decide_review

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def review_payload_gate(outcome, content, stale_branch):
    store = get_storage("memory")
    node = store.nodes.save(Node(title="gate-probe", content="seed", track="dynamic"))
    decide_review(store, node.id, outcome, now=NOW, content=content, stale_branch=stale_branch)
    return True
