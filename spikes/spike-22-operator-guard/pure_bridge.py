"""Process-only public alias for recording `zkc.tombstone._require_operator`.

Scope
-----
Expose the human-in-the-loop operator guard as a stable recording unit, so the
`tombstone.py` module (which also holds Storage/UUID/datetime-bound mark/restore)
is never bridged wholesale. Every decision is delegated verbatim to the Python
original.

No encoding seam: the argument is `str | None` and the return is `str`, both
native to the PyO3 JSON bridge. The alias exists only to pin the recording
surface to one function and avoid importing tombstone's Storage dependencies.

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`_require_operator(operator)` strips surrounding whitespace and returns the
result, or raises `ValueError` when the operator is empty/blank/None. The exact
Chinese contract text and the Python `str.isspace()` semantics are the original's.

Production boundary
-------------------
This slice proves only the deterministic operator-guard function. The callers
(`mark_tombstone` / `restore_node`) eat Storage/UUID/datetime and stay in Python
per Q5=C. The ADR-0013 human-in-the-loop contract is the truth source; this
alias is not production code. Deleting it only breaks re-recording and the kill
switch, not the Rust port itself.
"""
from zkc.tombstone import _require_operator as _require_operator


def require_operator(operator):
    return _require_operator(operator)
