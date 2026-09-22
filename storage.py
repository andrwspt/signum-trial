"""v12 Storage — SQLite backbone for Signum.

Tables: documents, chunks, clusters, links_v2, tags, conflicts, dynamics_log, notes_fts.

Vectors stored as JSON text (portable, no extension needed). Brute-force
cosine search in Python — fine for thousands of chunks; a vector index
comes later if scale demands it.
"""
from __future__ import annotations
import os
import json
import sqlite3
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

TZ = timezone(timedelta(hours=7))

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    folder TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created TEXT NOT NULL,
    modified TEXT NOT NULL,
    hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    note_id TEXT,
    start INTEGER NOT NULL DEFAULT 0,
    end INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    vector TEXT,
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    boundary_strength REAL DEFAULT 0.0,
    cluster INTEGER DEFAULT -1,
    source TEXT DEFAULT 'auto',
    created TEXT NOT NULL,
    summary TEXT,
    source_doc_id TEXT,
    source_offset_start INTEGER,
    source_offset_end INTEGER,
    source_version INTEGER DEFAULT 1,
    access_count INTEGER DEFAULT 0,
    last_accessed TEXT,
    activation REAL DEFAULT 1.0,
    pinned BOOLEAN DEFAULT FALSE,
    pos_x REAL,
    pos_y REAL,
    pos_z REAL,
    author TEXT DEFAULT 'andrew',
    tenant_id TEXT DEFAULT 'default',
    FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    centroid TEXT,
    member_count INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS links_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_chunk_id TEXT NOT NULL,
    target_chunk_id TEXT NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'references',
    weight REAL DEFAULT 0.5,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_chunk_id TEXT NOT NULL,
    target_chunk_id TEXT NOT NULL,
    link_term TEXT,
    FOREIGN KEY (source_chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,
    FOREIGN KEY (target_chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    usage_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    path TEXT,
    content TEXT,
    version INTEGER DEFAULT 1,
    hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    author TEXT DEFAULT 'andrew',
    tenant_id TEXT DEFAULT 'default'
);

CREATE TABLE IF NOT EXISTS conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_a_id TEXT NOT NULL,
    chunk_b_id TEXT NOT NULL,
    similarity REAL,
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved BOOLEAN DEFAULT FALSE,
    resolution TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS dynamics_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_value REAL,
    new_value REAL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    note_id, filename, content
);

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(note_id, filename, content) VALUES (new.id, new.filename, new.content);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    DELETE FROM notes_fts WHERE note_id = old.id;
END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
    UPDATE notes_fts SET filename = new.filename, content = new.content WHERE note_id = new.id;
END;
"""


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def cos(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@contextmanager
def open_db(db_path: str):
    """Yield a connection with row_factory, close on exit."""
    db_path = os.path.abspath(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def migrate_v11_to_v12(conn):
    """Ensure v12 columns exist on chunks table."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()]
    if "summary" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN summary TEXT")
    if "source_doc_id" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN source_doc_id TEXT")
    if "source_offset_start" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN source_offset_start INTEGER")
    if "source_offset_end" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN source_offset_end INTEGER")
    if "source_version" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN source_version INTEGER DEFAULT 1")
    if "access_count" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN access_count INTEGER DEFAULT 0")
    if "last_accessed" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN last_accessed TEXT")
    if "activation" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN activation REAL DEFAULT 1.0")
    if "pinned" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN pinned BOOLEAN DEFAULT FALSE")
    if "pos_x" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN pos_x REAL")
    if "pos_y" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN pos_y REAL")
    if "pos_z" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN pos_z REAL")
    if "author" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN author TEXT DEFAULT 'andrew'")
    if "tenant_id" not in cols:
        conn.execute("ALTER TABLE chunks ADD COLUMN tenant_id TEXT DEFAULT 'default'")
    conn.commit()


def note_id_for(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:19]


def chunk_id_for(note_id: str, start: int, end: int) -> str:
    return f"c{hashlib.sha256(f'{note_id}:{start}:{end}'.encode()).hexdigest()[:17]}"


# ---------------------------------------------------------------- notes


def save_note(conn, path: str, folder: str, filename: str,
              content: str, tags: Any = None, metadata: Any = None) -> str:
    tags_j = json.dumps(tags or [])
    meta_j = json.dumps(metadata or {})
    h = _hash(content)
    now = _now()
    nid = note_id_for(path)

    existing = conn.execute("SELECT id, hash FROM notes WHERE path = ?", (path,)).fetchone()
    if existing and existing["hash"] == h:
        return existing["id"]

    if existing:
        conn.execute(
            "UPDATE notes SET content=?, modified=?, hash=?, tags=?, metadata=? WHERE id=?",
            (content, now, h, tags_j, meta_j, nid),
        )
    else:
        conn.execute(
            "INSERT INTO notes (id, path, folder, filename, content, tags, metadata, created, modified, hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (nid, path, folder, filename, content, tags_j, meta_j, now, now, h),
        )
    return nid


def get_note(conn, note_id: str = None, path: str = None) -> Optional[Dict[str, Any]]:
    if note_id is not None:
        r = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    elif path is not None:
        r = conn.execute("SELECT * FROM notes WHERE path = ?", (path,)).fetchone()
    else:
        return None
    return dict(r) if r else None


def list_notes(conn, folder: Optional[str] = None) -> List[Dict[str, Any]]:
    if folder:
        rows = conn.execute(
            "SELECT id, path, folder, filename, tags, created, modified FROM notes WHERE folder = ? ORDER BY modified DESC",
            (folder,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, path, folder, filename, tags, created, modified FROM notes ORDER BY modified DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_folders(conn) -> List[str]:
    rows = conn.execute("SELECT DISTINCT folder FROM notes ORDER BY folder").fetchall()
    return [r["folder"] for r in rows]


def delete_note(conn, path: str):
    conn.execute("DELETE FROM notes WHERE path = ?", (path,))


# ---------------------------------------------------------------- documents


def save_document(conn, path: str, content: str, author: str = "andrew",
                  tenant_id: str = "default") -> str:
    """Save a document. Returns document id."""
    h = _hash(content)
    did = hashlib.sha256(path.encode()).hexdigest()[:19]
    now = _now()

    existing = conn.execute("SELECT id, hash FROM documents WHERE path = ?", (path,)).fetchone()
    if existing and existing["hash"] == h:
        return existing["id"]

    if existing:
        conn.execute(
            "UPDATE documents SET content=?, hash=?, version=version+1, updated_at=? WHERE id=?",
            (content, h, now, did)
        )
    else:
        conn.execute(
            "INSERT INTO documents (id, path, content, hash, author, tenant_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (did, path, content, h, author, tenant_id, now, now)
        )
    return did


def get_document(conn, doc_id: str) -> Optional[Dict[str, Any]]:
    """Get document by id."""
    r = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(r) if r else None


def get_document_chunks(conn, doc_id: str) -> List[Dict[str, Any]]:
    """Get all chunks for a document, ordered by offset."""
    rows = conn.execute(
        "SELECT * FROM chunks WHERE source_doc_id = ? ORDER BY source_offset_start",
        (doc_id,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("vector"):
            try:
                d["vector"] = json.loads(d["vector"])
            except (json.JSONDecodeError, TypeError):
                d["vector"] = None
        if d.get("tags"):
            try:
                d["tags"] = json.loads(d["tags"])
            except (json.JSONDecodeError, TypeError):
                pass
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(d)
    return out


# ---------------------------------------------------------------- chunks


def save_chunks(conn, note_id: str, chunks: List[Dict[str, Any]]) -> List[str]:
    """Bulk insert chunks. Returns list of chunk ids."""
    ids = []
    now = _now()
    for c in chunks:
        cid = chunk_id_for(note_id, c["start"], c["end"])
        vec_j = json.dumps(c.get("vector")) if c.get("vector") is not None else None
        conn.execute(
            "INSERT OR REPLACE INTO chunks (id, note_id, start, end, text, vector, tags, metadata, boundary_strength, cluster, source, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid, note_id, c["start"], c["end"], c["text"],
                vec_j,
                json.dumps(c.get("tags", []) or []),
                json.dumps(c.get("metadata", {}) or {}),
                c.get("boundary_strength", 0.0),
                c.get("cluster", -1),
                c.get("source", "auto"),
                now,
            ),
        )
        ids.append(cid)
    return ids


def get_chunks(conn, note_id: str = None, chunk_id: str = None) -> List[Dict[str, Any]]:
    if chunk_id is not None:
        rows = conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)).fetchall()
    elif note_id is not None:
        rows = conn.execute(
            "SELECT * FROM chunks WHERE note_id = ? ORDER BY start", (note_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM chunks ORDER BY created DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("vector"):
            try:
                d["vector"] = json.loads(d["vector"])
            except (json.JSONDecodeError, TypeError):
                d["vector"] = None
        if d.get("tags"):
            try:
                d["tags"] = json.loads(d["tags"])
            except (json.JSONDecodeError, TypeError):
                pass
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(d)
    return out


def get_chunk(conn, chunk_id: str) -> Optional[Dict[str, Any]]:
    rows = get_chunks(conn, chunk_id=chunk_id)
    return rows[0] if rows else None


def update_chunk_cluster(conn, chunk_id: str, cluster_id: int):
    conn.execute("UPDATE chunks SET cluster = ? WHERE id = ?", (cluster_id, chunk_id))


def update_chunk_boundary(conn, chunk_id: str, start: int, end: int, vector: Any = None):
    sets = ["start = ?", "end = ?"]
    vals = [start, end]
    if vector is not None:
        sets.append("vector = ?")
        vals.append(json.dumps(vector) if vector is not None else None)
    vals.append(chunk_id)
    conn.execute(f"UPDATE chunks SET {', '.join(sets)} WHERE id = ?", vals)


def delete_chunks(conn, note_id: str):
    conn.execute("DELETE FROM chunks WHERE note_id = ?", (note_id,))


def get_all_chunks_vectors(conn) -> List[Tuple[str, List[float], Dict]]:
    """Return all chunks as (chunk_id, vector, payload) for clustering."""
    rows = conn.execute(
        "SELECT id, text, vector, note_id, start, end, tags, metadata, boundary_strength FROM chunks"
    ).fetchall()
    out = []
    for r in rows:
        vec = None
        if r["vector"]:
            try:
                vec = json.loads(r["vector"])
            except (json.JSONDecodeError, TypeError):
                pass
        out.append((
            r["id"],
            vec,
            {
                "text": r["text"],
                "note_id": r["note_id"],
                "start": r["start"],
                "end": r["end"],
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                "boundary_strength": r["boundary_strength"],
            },
        ))
    return out


# ---------------------------------------------------------------- typed links


def save_typed_link(conn, source_id: str, target_id: str, link_type: str = "references",
                    weight: float = 0.5) -> None:
    """Save a typed link between chunks."""
    conn.execute(
        "INSERT OR REPLACE INTO links_v2 (source_chunk_id, target_chunk_id, link_type, weight) VALUES (?,?,?,?)",
        (source_id, target_id, link_type, weight)
    )


def get_chunk_links(conn, chunk_id: str, direction: str = "both") -> List[Dict[str, Any]]:
    """Get typed links for a chunk.
    direction: 'outgoing', 'incoming', or 'both'
    """
    if direction == "outgoing":
        rows = conn.execute(
            "SELECT * FROM links_v2 WHERE source_chunk_id = ?", (chunk_id,)
        ).fetchall()
    elif direction == "incoming":
        rows = conn.execute(
            "SELECT * FROM links_v2 WHERE target_chunk_id = ?", (chunk_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM links_v2 WHERE source_chunk_id = ? OR target_chunk_id = ?",
            (chunk_id, chunk_id)
        ).fetchall()
    return [dict(r) for r in rows]


def strengthen_link(conn, source_id: str, target_id: str, delta: float = 0.1) -> None:
    """Strengthen a link (Hebbian learning)."""
    conn.execute(
        "UPDATE links_v2 SET weight = MIN(1.0, weight + ?) WHERE source_chunk_id = ? AND target_chunk_id = ?",
        (delta, source_id, target_id)
    )


def decay_links(conn, decay_rate: float = 0.01) -> None:
    """Decay all unused links."""
    conn.execute(
        "UPDATE links_v2 SET weight = MAX(0.0, weight - ?) WHERE weight > 0",
        (decay_rate,)
    )


# ---------------------------------------------------------------- activation dynamics


def record_chunk_access(conn, chunk_id: str) -> None:
    """Record that a chunk was accessed (increment count, update timestamp, boost activation)."""
    conn.execute(
        "UPDATE chunks SET access_count = access_count + 1, last_accessed = ?, activation = MIN(1.0, activation + 0.1) WHERE id = ?",
        (_now(), chunk_id)
    )


def decay_activations(conn, decay_rate: float = 0.02) -> None:
    """Decay all unpinned chunk activations."""
    conn.execute(
        "UPDATE chunks SET activation = MAX(0.0, activation - ?) WHERE pinned = FALSE",
        (decay_rate,)
    )


def get_hot_chunks(conn, limit: int = 10) -> List[Dict[str, Any]]:
    """Get chunks with highest activation."""
    rows = conn.execute(
        "SELECT id, text, activation FROM chunks ORDER BY activation DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def log_dynamics(conn, chunk_id: str, event_type: str,
                 old_value: Optional[float] = None, new_value: Optional[float] = None) -> None:
    """Log a dynamics event."""
    conn.execute(
        "INSERT INTO dynamics_log (chunk_id, event_type, old_value, new_value) VALUES (?,?,?,?)",
        (chunk_id, event_type, old_value, new_value)
    )


# ---------------------------------------------------------------- chunk-to-document sync


def chunk_to_document_sync(conn, chunk_id: str, new_text: str) -> bool:
    """Sync a chunk edit back to its source document."""
    chunk = conn.execute(
        "SELECT * FROM chunks WHERE id = ?", (chunk_id,)
    ).fetchone()
    if not chunk or not chunk["source_doc_id"]:
        return False

    doc_id = chunk["source_doc_id"]
    doc = get_document(conn, doc_id)
    if not doc:
        return False

    old_text = chunk["text"]
    old_len = chunk["source_offset_end"] - chunk["source_offset_start"]
    new_len = len(new_text)
    delta = new_len - old_len

    # Update document content
    content = doc["content"]
    new_content = content[:chunk["source_offset_start"]] + new_text + content[chunk["source_offset_end"]:]
    conn.execute(
        "UPDATE documents SET content=?, version=version+1, updated_at=? WHERE id=?",
        (new_content, _now(), doc_id)
    )

    # Update chunk
    conn.execute(
        "UPDATE chunks SET text=?, source_offset_end=?, created=? WHERE id=?",
        (new_text, chunk["source_offset_end"] + delta, _now(), chunk_id)
    )

    # Shift subsequent chunks
    if delta != 0:
        conn.execute(
            "UPDATE chunks SET source_offset_start = source_offset_start + ?, source_offset_end = source_offset_end + ? WHERE source_doc_id = ? AND source_offset_start > ?",
            (delta, delta, doc_id, chunk["source_offset_start"])
        )

    log_dynamics(conn, chunk_id, "edit", old_text[:50], new_text[:50])
    return True


# ---------------------------------------------------------------- conflict detection


def detect_conflicts(conn, chunk_id: str, threshold: float = 0.85) -> List[Dict[str, Any]]:
    """Detect contradictions for a chunk.
    
    1. Find most similar chunks
    2. Check if they contradict (high similarity but opposing content)
    3. Create conflict records
    """
    chunk = conn.execute("SELECT id, text, vector FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
    if not chunk or not chunk["vector"]:
        return []

    vec = json.loads(chunk["vector"])
    all_chunks = conn.execute(
        "SELECT id, text, vector FROM chunks WHERE id != ? AND vector IS NOT NULL",
        (chunk_id,)
    ).fetchall()

    conflicts = []
    for other in all_chunks:
        other_vec = json.loads(other["vector"])
        sim = cos(vec, other_vec)

        if sim > threshold:
            is_contradiction = _check_contradiction(chunk["text"], other["text"])
            if is_contradiction:
                conn.execute(
                    "INSERT INTO conflicts (chunk_a_id, chunk_b_id, similarity) VALUES (?,?,?)",
                    (chunk_id, other["id"], sim)
                )
                conflicts.append({
                    "chunk_a": chunk_id,
                    "chunk_b": other["id"],
                    "similarity": sim,
                })

    return conflicts


def _check_contradiction(text_a: str, text_b: str) -> bool:
    """Simple heuristic for contradiction detection.
    Returns True if texts likely contradict.
    """
    negation_words = ["not", "no", "never", "cannot", "don't", "doesn't", "isn't", "aren't", "won't"]

    a_has_neg = any(w in text_a.lower() for w in negation_words)
    b_has_neg = any(w in text_b.lower() for w in negation_words)

    if a_has_neg != b_has_neg:
        a_clean = " ".join(w for w in text_a.lower().split() if w not in negation_words)
        b_clean = " ".join(w for w in text_b.lower().split() if w not in negation_words)

        a_words = set(a_clean.split())
        b_words = set(b_clean.split())
        if a_words and b_words:
            overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
            return overlap > 0.7

    return False


# ---------------------------------------------------------------- clusters


def save_cluster(conn, cid: int, name: str, centroid: Any = None,
                 member_count: int = 0, tags: Any = None, metadata: Any = None):
    cent_j = json.dumps(centroid) if centroid is not None else None
    tags_j = json.dumps(tags or [])
    meta_j = json.dumps(metadata or {})
    conn.execute(
        "INSERT OR REPLACE INTO clusters (id, name, centroid, member_count, tags, metadata) VALUES (?,?,?,?,?,?)",
        (cid, name, cent_j, member_count, tags_j, meta_j),
    )


def get_clusters(conn) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM clusters ORDER BY id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("centroid"):
            try:
                d["centroid"] = json.loads(d["centroid"])
            except (json.JSONDecodeError, TypeError):
                d["centroid"] = None
        if d.get("tags"):
            try:
                d["tags"] = json.loads(d["tags"])
            except (json.JSONDecodeError, TypeError):
                pass
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(d)
    return out


def clear_clusters(conn):
    conn.execute("DELETE FROM clusters")


# ---------------------------------------------------------------- links (legacy)


def save_link(conn, source_chunk_id: str, target_chunk_id: str, link_term: str = None):
    conn.execute(
        "INSERT OR IGNORE INTO links (source_chunk_id, target_chunk_id, link_term) VALUES (?,?,?)",
        (source_chunk_id, target_chunk_id, link_term),
    )


def get_links_for_chunk(conn, chunk_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM links WHERE source_chunk_id = ? OR target_chunk_id = ?",
        (chunk_id, chunk_id),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_links_for_chunk(conn, chunk_id: str):
    conn.execute("DELETE FROM links WHERE source_chunk_id = ? OR target_chunk_id = ?",
                         (chunk_id, chunk_id))


# ---------------------------------------------------------------- tags


def upsert_tags(conn, tags: List[str]):
    for t in set(tags or []):
        name = str(t).strip()
        if not name:
            continue
        conn.execute(
            "INSERT INTO tags (name, usage_count) VALUES (?, 1) "
            "ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1",
            (name,),
        )


def list_tags(conn) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT name, usage_count FROM tags ORDER BY usage_count DESC, name").fetchall()
    return [{"name": r["name"], "usage_count": r["usage_count"]} for r in rows]


# ---------------------------------------------------------------- search


def search_keyword(conn, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT n.id, n.path, n.folder, n.filename, "
            "snippet(notes_fts, 2, '<b>', '</b>', '...', 30) as snip, notes_fts.rank as rank "
            "FROM notes_fts JOIN notes n ON notes_fts.note_id = n.id "
            "WHERE notes_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["snippet"] = r["snip"]
            del d["snip"]
            out.append(d)
        return out
    except Exception:
        return []


def search_chunks_semantic(conn, vector: List[float], limit: int = 20) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT c.id, c.text, c.note_id, c.start, c.end, c.boundary_strength, c.cluster, "
        "n.path, n.folder, n.filename FROM chunks c JOIN notes n ON c.note_id = n.id"
    ).fetchall()
    results = []
    for r in rows:
        vec = None
        if r["vector"] if "vector" in r else None:
            pass
        # vector stored in chunks.vector column (JSON) — reload from row
        vec_j = conn.execute("SELECT vector FROM chunks WHERE id = ?", (r["id"],)).fetchone()[0]
        if vec_j:
            try:
                vec = json.loads(vec_j)
            except (json.JSONDecodeError, TypeError):
                vec = None
        if vec is None:
            continue
        sim = cos(vector, vec)
        results.append({
            "chunk_id": r["id"],
            "note_id": r["note_id"],
            "text": r["text"],
            "path": r["path"],
            "folder": r["folder"],
            "filename": r["filename"],
            "start": r["start"],
            "end": r["end"],
            "boundary_strength": r["boundary_strength"],
            "cluster": r["cluster"],
            "similarity": round(sim, 4),
        })
    results.sort(key=lambda x: -x["similarity"])
    return results[:limit]


def reindex_fts(conn):
    """Rebuild the FTS index from notes."""
    conn.execute("DELETE FROM notes_fts")
    rows = conn.execute("SELECT id, filename, content FROM notes").fetchall()
    for r in rows:
        conn.execute("INSERT INTO notes_fts(note_id, filename, content) VALUES (?,?,?)",
                     (r["id"], r["filename"], r["content"]))
