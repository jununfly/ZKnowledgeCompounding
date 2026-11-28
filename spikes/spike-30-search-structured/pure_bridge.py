"""Process-only recording surface for `MemoryNodeRepository.search` (structured path, ticket 50 prereq).

Scope
-----
`filter_sort_nodes(nodes, track, q, decay_min, decay_max, include_archived, order, limit) -> list[dict]`

Builds a real `MemoryNodeRepository` from JSON node records and calls the ORIGINAL `search`
verbatim: tombstone/archive visibility, `track` equality, decay range (COALESCE null→0.0),
`q` case-insensitive substring over `title + "\\n" + content`, order validation, sort, and
`max(1, limit)` truncation.

Bounded to a canonical datetime form (Q5-style carve-out)
---------------------------------------------------------
`created_asc`/`created_desc` sort on the aware `datetime` `created_at`. To keep the recording
JSON-native and the ordering decidable, every `created_at` here is a fixed-format UTC ISO-8601
string (`...+00:00`), for which lexicographic order == chronological order; a missing/null
`created_at` maps to Python's `_MIN_DT` sentinel. Naive / non-UTC / mixed-offset datetimes and
non-ASCII Unicode case-folding edges of `.lower()` (e.g. `İ`, `ß`) are OUT of this slice — that
is the datetime/casefold encoding seam, not a portable behaviour. The pg.py SQL path (ILIKE,
COALESCE, ORDER BY) and the `search_by_embedding` kNN (separate slice) are not covered here.
"""
from datetime import datetime, timezone
from uuid import UUID

from zkc.repository.memory import MemoryNodeRepository
from zkc.repository.models import Node

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def filter_sort_nodes(nodes, track, q, decay_min, decay_max, include_archived, order, limit):
    repo = MemoryNodeRepository()
    for d in nodes:
        nid = UUID(d["id"])
        ca = d.get("created_at")
        repo._rows[nid] = Node(
            id=nid,
            track=d.get("track", "unrouted"),
            title=d.get("title", ""),
            content=d.get("content"),
            decay_score=d.get("decay_score") or 0.0,
            created_at=datetime.fromisoformat(ca) if ca else None,
            archived_at=_TS if d.get("archived") else None,
            deleted_at=_TS if d.get("deleted") else None,
        )
    result = repo.search(
        track=track, q=q, decay_min=decay_min, decay_max=decay_max,
        include_archived=bool(include_archived), order=order, limit=limit,
    )
    return [{"id": str(n.id), "title": n.title, "track": n.track, "decay_score": n.decay_score,
             "created_at": _iso(n.created_at)} for n in result]
