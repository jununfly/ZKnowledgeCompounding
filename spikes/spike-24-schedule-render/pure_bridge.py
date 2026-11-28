"""Process-only public aliases for recording `scripts/daily_driver_schedule.py`'s
pure schtasks rendering functions.

Scope
-----
Expose the three pure, JSON-native render helpers as a stable recording unit:
- `build_task_action(wrapper: str) -> str`  (/tr action path quoting + guards)
- `build_register_command(wrapper, task_name, at) -> list[str]`
- `build_unregister_command(task_name) -> list[str]`

Every decision is delegated verbatim to the Python original. No encoding seam:
str/list[str] arguments and str/list[str]/ValueError outputs are all native to
the PyO3 JSON bridge. `scripts/` is NOT a package, so the module is loaded by
absolute path via sys.path (same mechanism as tests/test_daily_driver_schedule.py).

Why this slice does not resolve D2
----------------------------------
The only real dynamic-code seam in scripts/ is `daily_e1_driver._import_meter`
(spec_from_file_location + exec_module), which is on NONE of these functions'
import paths. This module's top level is static imports + constants + a
`Path(__file__).resolve()` (no eval/exec/dynamic import). Porting these render
helpers does NOT consume or close DP ticket 13 (scripts dynamic-code blocker),
which remains owned by task 5 and unchanged.

Production boundary
-------------------
`main()` (argparse + subprocess.run + injectable runner/out), real Windows
schtasks registration, `resolve_paths()` (sys.executable) and the ADR-0007
cross-platform installer stay in Python. This slice proves only deterministic
command rendering; it is NOT a claim that registration works on Windows.
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import daily_driver_schedule as _sched  # noqa: E402


def build_task_action(wrapper):
    return _sched.build_task_action(wrapper)


def build_register_command(wrapper, task_name, at):
    return _sched.build_register_command(wrapper, task_name, at)


def build_unregister_command(task_name):
    return _sched.build_unregister_command(task_name)
