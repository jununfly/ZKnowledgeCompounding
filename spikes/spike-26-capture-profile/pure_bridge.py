"""Process-only public alias for recording `zkc.mcp.capture.CaptureProfile.__post_init__`.

Scope
-----
Expose the capture-profile write-set invariant as a stable, JSON-native recording unit:

- `validate_capture_profile(allowed: list[str], forbidden: list[str]) -> bool`

It constructs the real `CaptureProfile` dataclass, so the overlap check (`__post_init__`)
runs verbatim from the Python original: a non-empty `allowed_writes ∩ forbidden_writes`
raises `ValueError` (recorded as a throw), otherwise the profile is valid and returns `True`.
The arguments are JSON lists (converted to `frozenset` here); the only decision is delegated.

Why only this slice from `capture.py`
-------------------------------------
`capture_documents` and its `initialize_decay` are out of scope: they bind callables
(`audit_sink`, routers), `Storage` (`store`), `datetime.now`, and the domain `node` object —
the same dataclass/Storage encoding seam Q5 left in Python. `initialize_decay` is also a thin
delegate to `decay.compute_decay_score`, already ported in `decay-rs`. This slice covers only
the self-contained safety-contract validation gate.

Nothing here is production code; the write-allowlist / blacklist / HITL enforcement stays in
Python (`handlers.py`). The recorded literals are the security contract, not a new policy source.
"""
from zkc.mcp.capture import CaptureProfile as _CaptureProfile


def validate_capture_profile(allowed, forbidden):
    _CaptureProfile(allowed_writes=frozenset(allowed), forbidden_writes=frozenset(forbidden))
    return True
