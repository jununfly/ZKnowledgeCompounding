"""Process-only public alias for recording `zkc.r14_telemetry._validate_report`.

Scope
-----
Expose the single pure R14 report-validation helper as a stable recording unit,
so `r14_telemetry.py` (which also holds file-IO `record_run` / `load_runs` /
`aggregate`) is never bridged wholesale. Every decision is delegated verbatim
to the Python original.

No encoding seam: the argument is `dict` and the return is `None` (or a
`ValueError`), all native to the PyO3 JSON bridge. The alias exists only to pin
the recording surface to one function. The `REQUIRED_FIELDS` constant it reads
is a module-level immutable tuple, matching the `INJECTION_MARKERS` precedent.

Production boundary
-------------------
This slice proves only the deterministic field-presence check. It is NOT an
R14-close runtime guarantee: real runs are produced by zj via dogfood and
persisted by `record_run` (file IO), remaining in Python per the Q5 file-IO
boundary in `finding-r14-judgment-boundary.md`. Nothing here is production code;
deleting it only breaks re-recording and the kill switch, not the Rust port.
"""
from zkc.r14_telemetry import _validate_report as _validate_report


def validate_report(report):
    return _validate_report(report)
