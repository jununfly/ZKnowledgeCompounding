"""Process-only public alias for recording `zkc.scheduling._percentile`.

Scope
-----
Expose the L2 budget-percentile helper as a stable recording unit, so the mixed
`src/zkc/scheduling.py` module (which also holds dataclass/Storage-bound budget
functions) is never bridged wholesale. Every decision is delegated verbatim to
the Python original.

No encoding seam: the argument is `list[float]` + `float` and the return is
`float`, all native to the PyO3 JSON bridge. The alias exists only to pin the
recording surface to one function and avoid importing scheduling's tuning globals.

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`_percentile(values, q)` sorts a copy, returns the single element for len==1,
otherwise linearly interpolates at `pos = q * (len-1)` with `int` truncation.
An empty list raises `IndexError: list index out of range`. Nothing here
redefines the math or the threshold semantics.

Production boundary
-------------------
This slice proves only the deterministic percentile math. The public callers
(`estimate_budget_from` / `update_budget_from`) eat `AttentionObservation`
dataclasses and stay in Python per `finding-interval-math-boundary.md`.
Tuning globals (MIN/MAX_INTERVAL, AIMD, ROT_THRESHOLD) are out of scope.

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from zkc.scheduling import _percentile as _percentile


def percentile(values, q):
    return _percentile(values, q)
