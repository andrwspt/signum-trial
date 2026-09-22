"""v11 Auto-update — polling-based change detection.

The client polls /api/digest every N seconds. If the digest changes,
it refreshes affected panels. This module provides the server-side
digest computation.
"""
from __future__ import annotations
import hashlib
import json
from typing import Dict, Any

_storage = None
def _get_storage():
    global _storage
    if _storage is None:
        import storage as _s
        _storage = _s
    return _storage

def compute_digest(db_path: str) -> Dict[str, Any]:
    """Compute a change-detecting digest of the current DB state.

    Returns:
        {
            "digest": str,       # short hash of the full state
            "notes_count": int,
            "chunks_count": int,
            "clusters_count": int,
            "tags_count": int,
            "last_note_modified": str,
            "state": dict,       # full state for the client to use directly
        }
    """
    with _get_storage().open_db(db_path) as conn:
        notes = _get_storage().list_notes(conn)
        chunks = _get_storage().get_chunks(conn)
        clusters = _get_storage().get_clusters(conn)
        tags = _get_storage().list_tags(conn)

    notes_count = len(notes)
    chunks_count = len(chunks)
    clusters_count = len(clusters)
    tags_count = len(tags)
    last_modified = ""
    for n in notes:
        m = n.get("modified", "")
        if m > last_modified:
            last_modified = m

    state = {
        "notes": notes,
        "chunks": chunks,
        "clusters": clusters,
        "tags": tags,
    }
    payload = json.dumps(state, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]

    return {
        "digest": digest,
        "notes_count": notes_count,
        "chunks_count": chunks_count,
        "clusters_count": clusters_count,
        "tags_count": tags_count,
        "last_note_modified": last_modified,
        "state": state,
    }
