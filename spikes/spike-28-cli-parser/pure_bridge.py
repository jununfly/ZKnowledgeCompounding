"""Process-only public alias for recording `zkc.cli.parse_args` (valid-argv mapping).

Scope
-----
`parse_argv(argv: list[str]) -> dict` returns `vars(parse_args(argv))` — the parsed namespace as a
flat JSON-native dict (values are `str` / `bool` / `None` only: subcommand names, `--storage`
strings, `store_true` flags `--json/--list/--corpus/--dry-run`, optional `--id/--content/
--verdict/--stale-branch/--operator/--reason`). It delegates to the REAL parser, so defaults,
subparser dispatch (incl. the nested `tombstone mark|restore|sweep`), and `choices` acceptance all
run verbatim from `cli.py`.

Bounded to VALID argv
--------------------
Only canonical, valid argv is recorded. argparse's error surface is a *library encoding seam*
(finding 26) and is deliberately OUT of this slice: on invalid/missing/required args argparse calls
`parser.error()` → prints usage to stderr → `SystemExit(2)`, and it also does unique-prefix option
matching (`--stor`→`--storage`). None of that is a JSON-in/JSON-out behaviour, so this port claims
equivalence **only for the valid-argv → namespace-dict mapping**, not for argparse's usage/SystemExit
or abbreviation semantics — consistent with the Q5 "tool/library boundary" ruling.

Nothing here is production code; the CLI grammar stays defined in `cli.py`.
"""
from zkc.cli import parse_args


def parse_argv(argv):
    return vars(parse_args(list(argv)))
