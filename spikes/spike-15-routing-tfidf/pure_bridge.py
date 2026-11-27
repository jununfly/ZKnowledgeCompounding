"""Process-only public aliases for recording `zkc.routing`'s lexical TF-IDF layer.

Scope
-----
The Rust port takes JSON scalars / strings / string lists / string-keyed float
maps through the PyO3 bridge. This adapter exposes the three deterministic
literal-TF-IDF functions of `src/zkc/routing.py`, which is the embedding-free
second signal of ZKC's dual-track router. Every decision is delegated verbatim
to the Python original; the adapter only gives the bridge three public names.

Alias map (encoding seam, not decision behavior)
------------------------------------------------
- `tokenize(text)`       -> `zkc.routing._tokenize(text)`
- `tfidf_vector(t, idf)` -> `zkc.routing._tfidf_vector(t, idf)`
- `cosine(a, b)`         -> `zkc.routing._cosine(a, b)`

Recorded vocabulary (delegated, not reimplemented)
--------------------------------------------------
`_tokenize` applies `text.lower()` then `_TOKEN_RE = [a-z0-9]+|[\\u4e00-\\u9fff]`:
ASCII lowercase letters/digits are grouped into runs, each CJK unified ideograph
in U+4E00..U+9FFF is emitted one character at a time, and every other character
(including uppercase before lowering, whitespace, punctuation and emoji) is
discarded. The regex source and the lowercasing step are **recorded literals**
from the original; the Rust port annotates them as `recorded-literal`.

`_tfidf_vector` builds `tf[t] = tf.get(t, 0.0) + 1.0` in token order, sets
`n = len(tokens) or 1`, then returns `{t: (c / n) * idf.get(t, 0.0) for t, c in
tf.items()}`. The insertion order is the first-occurrence order of tokens; the
JSON comparison preserves key order, so the Rust side must use an order-preserving
map. Missing idf keys contribute 0.0; an empty token list yields an empty map.

`_cosine` takes `common = set(a) & set(b)`. With no common key it returns 0.0;
otherwise `dot = sum(a[t] * b[t] for t in common)`, `na = sqrt(sum(v*v for v in
a.values()))`, `nb = sqrt(sum(v*v for v in b.values()))`; `na == 0 or nb == 0`
returns 0.0, else `dot / (na * nb)`. The set iteration order is an encoding-level
hazard when three or more keys are common: Python's string hash is salted per
process, so addition order (and thus the last float bit) can differ between the
recording process and the oracle process. Recorded cases deliberately include
three-plus-key intersections to expose, not hide, that difference.

Decision table under test
-------------------------
1. Repeated tokens raise tf but the divisor is the full token count including
   duplicates; a token absent from idf contributes exactly 0.0.
2. Zero-norm maps return 0.0 even when keys intersect.
3. Disjoint maps return 0.0 without computing norms.
4. `_cosine` is symmetric at the value level; key iteration order must not be
   mistaken for a policy decision.

Recording contract
------------------
`rust-anything record --count 0 --inputs tmp/routing-inputs.jsonl` freezes
targeted cases: empty/whitespace/punctuation/emoji text, mixed English digits and
Chinese, Unicode lowercasing edge cases (`İ`, `ß`), `n=0` empty token list,
idf hits/misses, duplicate tokens, disjoint maps, zero vectors, and three-plus
common keys for the floating-point addition order.

Production boundary
-------------------
`route_text`, `LexicalRouter.fit/predict`, `DecisionRouter`, `ChatClient`,
`OllamaClient`, tuning gates and `lexical_corpus` persistence stay in Python.
This slice proves literal numeric behavior only; it is not a routing release,
not a safety decision, and does not turn corpus-derived gates into CALIBRATED
tuning values.

Nothing in this adapter is production code. Deleting it only breaks re-recording
and the kill switch, not the Rust port itself.
"""
from zkc import routing as _routing


def tokenize(text):
    return _routing._tokenize(text)


def tfidf_vector(tokens, idf):
    return _routing._tfidf_vector(tokens, idf)


def cosine(a, b):
    return _routing._cosine(a, b)
