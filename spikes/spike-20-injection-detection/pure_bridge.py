"""Process-only public alias for recording `zkc.mcp.injection.detect_injection_markers`.

Scope
-----
Expose the single pure injection-marker detection function as a stable recording
unit, so the mixed `src/zkc/mcp/` unit (which also holds callable/Storage-bound
handlers) is never bridged wholesale. Every decision is delegated verbatim to the
Python original.

Unlike the recent artifact/distill/cross-source aliases, this function has NO
encoding seam: its argument is `str` and its return is `List[str]`, both native
to the PyO3 JSON bridge. The alias exists only to pin the recording surface to
one function.

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`detect_injection_markers(text)` lowercases the input and returns the markers
from `INJECTION_MARKERS` that appear as substrings, in declaration order and
deduplicated; empty text returns []. The 14 marker strings and the matching rule
stay the original's; nothing here redefines the security contract.

Production boundary
-------------------
This slice proves only the deterministic detection function. Detection is used
for logging/marking only — never as executable instructions. Whitelists, blacklists
and the HITL attribution gate live in `handlers.py` and stay in Python. `capture_documents`
and the server builders (callable / Storage / CaptureProfile dataclass) are out of scope.

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from zkc.mcp.injection import detect_injection_markers as _detect_injection_markers


def detect_injection_markers(text):
    return _detect_injection_markers(text)
