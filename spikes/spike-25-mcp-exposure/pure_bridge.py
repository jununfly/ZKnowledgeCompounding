"""Process-only public aliases for recording `zkc.mcp.exposure` attack-surface table.

Scope
-----
Expose the two pure, JSON-native entry points of the MCP attack-surface enumeration
(`ADR-0004` mandatory section) as a stable recording unit:

- `attack_surface_table() -> dict`   (deep copy of `ATTACK_SURFACE`)
- `entry_names() -> list[str]`       (ordered entry-point names)

Every decision is delegated verbatim to the Python original. No encoding seam: both
take zero arguments and return only `str` / `list` / `dict` built from `zkc.transport.contract`
constants (`TOOL_NAMES` / `BLACKLIST` / `TRUST_BOUNDARY`), which `rust/transport-rs` has
already ported and recorded (`contract_snapshot` / `is_blacklisted` / `is_allowlisted`).
The alias exists only to pin the recording surface to these two functions instead of the
mixed `src/zkc/mcp/` unit (which also holds callable/Storage/`datetime`-bound handlers).

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`attack_surface_table` returns a structural copy: `entry` (one row per whitelisted tool
with `name`/`kind`/`guard`), empty `egress` (single-sided server), `trustBoundary` string,
sorted `blacklist`, and the fixed `injectionGate` assertions. `entry_names` projects the
`entry` names in `TOOL_NAMES` declaration order. The guards / kinds / texts are recorded
literals from the security contract, never a new policy source.

Production boundary
-------------------
This slice proves only the deterministic table projection. The table is documentation /
contract metadata; the enforcement (whitelist routing, HITL attribution gate, blacklisting)
lives in `handlers.py` and stays in Python. `capture_documents`, `build_handlers`,
`build_zkc_server` (callable / Storage / CaptureProfile dataclass) are out of scope.

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from zkc.mcp.exposure import attack_surface_table as _attack_surface_table
from zkc.mcp.exposure import entry_names as _entry_names


def attack_surface_table():
    return _attack_surface_table()


def entry_names():
    return _entry_names()
