"""Process-only public aliases for recording `zkc.faithfulness`'s literal rubric.

Scope
-----
The Rust port takes JSON scalars / strings / string lists through the PyO3
bridge. This adapter exposes the seven deterministic literal-rubric functions
of `src/zkc/faithfulness.py`. It normalizes **only one bridge encoding** —
`_ngrams` returns a Python `set[str]`, which the JSON bridge cannot carry, so
the alias emits a sorted list. Every decision is delegated verbatim to the
Python original. It is not production code and not a migration target.

Normalization (encoding seam, not decision behavior)
-----------------------------------------------------
- `ngrams(text, n)` -> `sorted(_ngrams(text, n))`, a deterministic JSON form of
  the same set; ordering is imposed by the alias, not by the original.

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`_normalize` strips whitespace and these punctuation classes (from the
original `_PUNCT` regex): ASCII space/newline, Chinese comma/period/semicolon/
colon/enumeration/exclamation/question marks, ASCII comma/period/exclamation/
question mark/colon/semicolon, straight and curly double/single quotes,
Chinese and ASCII parentheses/brackets, em dash and hyphen. Other characters
(including emoji and non-listed Unicode punctuation) are preserved verbatim.

`_ngrams` slices the normalized text into overlapping `n`-character windows;
text shorter than `n` yields the single whole normalized string, and empty
normalized text yields an empty set (recorded here as an empty list).

`_lcs_length` normalizes both sides, truncates each to 600 characters, and
returns the longest common **substring** length (not subsequence).

Decision table under test
-------------------------
1. `verbatim_rate` is 0.0 for empty normalized claim, otherwise
   `min(1.0, max(LCS(claim, s) for s in sources, default=0) / len(normalized claim))`.
2. `overlap` is 0.0 when the claim has no 3-grams, otherwise
   `|grams(claim) & union(grams(s))| / |grams(claim)|`.
3. `rubric_flags` filters out blank source texts. With no non-blank source it
   returns exactly `["rubric_no_source_text"]`. Otherwise it appends
   `rubric_verbatim_{v:.2f}` when `v > FAITH_RUBRIC_VERBATIM_MAX` and
   `rubric_overlap_{o:.2f}` when `o > FAITH_RUBRIC_OVERLAP_MAX`, in that order.
4. `is_forced` is true for a route starting with `"forced"` or exactly equal
   to `"human_only"`; null and empty routes are false.

Threshold provenance (recorded-literal, never promoted here)
-------------------------------------------------------------
`FAITH_RUBRIC_VERBATIM_MAX = 0.5 (placeholder)` and
`FAITH_RUBRIC_OVERLAP_MAX = 0.7 (placeholder)` come from `zkc.tuning` at
recording time. The Rust port annotates them as `recorded-literal`; this slice
does not make them CALIBRATED. The `rubric_no_source_text`, `rubric_verbatim_`,
`rubric_overlap_` strings and the `forced` / `human_only` routes are likewise
recorded literals, not new policy.

Recording contract
------------------
`rust-anything record --count 0 --inputs tmp/faithfulness-inputs.jsonl` freezes
targeted cases for all seven functions: empty / whitespace / punctuation-only /
unicode / emoji / long (>600 char) texts, `n` from 1 to 5, exact copies and
partial rewrites, multiple sources, both rubric threshold sides, blank sources,
and every forced-route branch.

Production boundary
-------------------
`aggregate` (`AtomicFact` dataclass), `parse_judgment` (pydantic `Judgment`),
`build_judge_prompt` (long prompt text), and all Storage / LLM / callable /
datetime routing functions stay in Python. `gate_new_claims` is dogfood/test
only; rubric flags are pending-human annotations, never a release decision.

Nothing in this adapter is production code. Deleting it only breaks
re-recording and the kill switch, not the Rust port itself.
"""
from zkc import faithfulness as _faithfulness


def normalize(text):
    return _faithfulness._normalize(text)


def ngrams(text, n=3):
    return sorted(_faithfulness._ngrams(text, n))


def lcs_length(a, b):
    return _faithfulness._lcs_length(a, b)


def verbatim_rate(claim, source_texts):
    return _faithfulness.verbatim_rate(claim, source_texts)


def overlap(claim, source_texts):
    return _faithfulness.overlap(claim, source_texts)


def rubric_flags(claim_text, source_texts):
    return _faithfulness.rubric_flags(claim_text, source_texts)


def is_forced(route):
    return _faithfulness._is_forced(route)
