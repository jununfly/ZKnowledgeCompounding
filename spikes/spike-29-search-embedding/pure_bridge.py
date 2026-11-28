"""Process-only recording surface for `MemoryNodeRepository.search_by_embedding` (ticket 50 prereq).

Scope
-----
`search_embedding_knn(nodes, vector, k, include_archived, column) -> list[{id, sim}]`

It builds a real `MemoryNodeRepository` from JSON node records and calls the ORIGINAL
`search_by_embedding` verbatim, so the cosine similarity, tombstone/archive visibility,
`column` validation and the top-k ordering all run from the Python original (memory.py is the
PG-isomorphic reference; pg.py runs the same contract via pgvector `<=>`).

Inputs are JSON-native:
  nodes  = [{"id": str, "embedding": list[float]|None, "embedding_4096": list[float]|None,
             "archived": bool, "deleted": bool}, ...]
  vector = list[float]
  k      = int, include_archived = bool, column = "embedding" | "embedding_4096"
Output preserves `[(node, sim)]` order: [{"id": ..., "sim": <float>}, ...] (raw cosine, not rounded —
the float bridge handles repr parity; `browse.py` rounds to 4 only at display time).

Why this slice (not the whole search)
-------------------------------------
`search_by_embedding` is pure float math over `Node.embedding` lists — no datetime ordering, no
external service. The `archived`/`deleted` booleans map to `archived_at`/`deleted_at` datetime
columns ONLY for null-vs-set visibility (their values never enter the output), so no datetime
encoding is exercised. The `pg.py` SQL path (pgvector `<=>`) and the `encoder`/`search()`
orchestration remain the Storage/A-path seam — this records only the canonical memory behaviour.
"""
from datetime import datetime, timezone
from uuid import UUID

from zkc.repository.memory import MemoryNodeRepository
from zkc.repository.models import Node

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def search_embedding_knn(nodes, vector, k, include_archived, column):
    repo = MemoryNodeRepository()
    for d in nodes:
        nid = UUID(d["id"])
        repo._rows[nid] = Node(
            id=nid,
            embedding=d.get("embedding"),
            embedding_4096=d.get("embedding_4096"),
            archived_at=_TS if d.get("archived") else None,
            deleted_at=_TS if d.get("deleted") else None,
        )
    result = repo.search_by_embedding(
        list(vector), k=k, include_archived=bool(include_archived), column=column
    )
    return [{"id": str(n.id), "sim": sim} for n, sim in result]
