"""Signum v11 — clean server, all endpoints working."""
from __future__ import annotations
import os, sys, json, argparse, threading, time, hashlib
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from socketserver import ThreadingTCPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = timezone(timedelta(hours=7))

# module globals (set by main)
_db_path = ""
_storage_mod = None
_embedder_mod = None
_chunker_mod = None
_splice_mod = None
_cluster_mod = None
_skinner_mod = None
_llm_parse_mod = None

def _import_all():
    global _storage_mod, _embedder_mod, _chunker_mod, _splice_mod, _cluster_mod, _skinner_mod, _llm_parse_mod
    import storage as _storage_mod
    import embedder as _embedder_mod
    import chunker as _chunker_mod
    import splice as _splice_mod
    import cluster as _cluster_mod
    import skinner as _skinner_mod
    import llm_parse as _llm_parse_mod

def _now():
    return datetime.now(TZ).isoformat(timespec="seconds")

class Pipeline:
    def __init__(self, db_path, embed_mode="miniml", cluster_threshold=0.75):
        self.db_path = db_path
        self.embed_mode = embed_mode
        self.cluster_threshold = cluster_threshold
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            self._embedder = _embedder_mod.get_embedder(self.embed_mode)
        return self._embedder

    def run(self, text, tags=None, metadata=None, parse=False, parse_backend=None):
        embedder = self._get_embedder()
        storage = _storage_mod
        db_path = self.db_path

        with storage.open_db(db_path) as conn:
            folder = "/"
            filename = f"input_{time.strftime('%Y%m%dT%H%M%S')}_{hashlib.md5(text.encode()).hexdigest()[:6]}.md"
            note_id = storage.save_note(conn, path=f"/{filename}", folder=folder, filename=filename,
                                        content=text, tags=tags, metadata=metadata)

            parsed_tags = list(tags or [])
            parsed_meta = dict(metadata or {})
            parse_result = None
            if parse:
                parse_result = _llm_parse_mod.parse_text(text, backend=parse_backend)
                for t in parse_result.get("tags", []):
                    if t not in parsed_tags:
                        parsed_tags.append(t)
                for k, v in parse_result.get("metadata", {}).items():
                    if k not in parsed_meta:
                        parsed_meta[k] = v
                storage.save_note(conn, path=f"/{filename}", folder=folder, filename=filename,
                                  content=text, tags=parsed_tags, metadata=parsed_meta)

            result = _chunker_mod.chunk_text(text, embedder.embed_words, tag_signals={})
            fragments = result["fragments"]
            frag_texts = [f["text"] for f in fragments]
            frag_vecs = embedder.embed_chunks(frag_texts)
            for f, v in zip(fragments, frag_vecs):
                f["vector"] = v

            merged = _splice_mod.splice(fragments, result["words"])
            merged_texts = [m["text"] for m in merged]
            merged_vecs = embedder.embed_chunks(merged_texts)
            for m, v in zip(merged, merged_vecs):
                m["vector"] = v

            # Also save as document for v12 features
            doc_id = storage.save_document(conn, f"/{filename}", text)
            chunk_ids = storage.save_chunks(conn, note_id, [
                {
                    "start": m["start"], "end": m["end"], "text": m["text"],
                    "vector": m["vector"], "tags": parsed_tags, "metadata": parsed_meta,
                    "boundary_strength": m.get("boundary_strength", 0.0),
                    "cluster": -1, "source": "auto",
                }
                for m in merged
            ])
            # Update chunks with source_doc_id and byte offsets
            for i, cid in enumerate(chunk_ids):
                m = merged[i]
                char_start = len(" ".join(result["words"][:m["start"]]))
                char_end = char_start + len(m["text"])
                conn.execute(
                    "UPDATE chunks SET source_doc_id=?, source_offset_start=?, source_offset_end=? WHERE id=?",
                    (doc_id, char_start, char_end, cid)
                )

            links = _splice_mod.build_links_for_storage(merged, chunk_ids)
            for lk in links:
                storage.save_link(conn, lk["source_chunk_id"], lk["target_chunk_id"], lk["link_term"])

            cl_result = _cluster_mod.cluster_all(merged_vecs, self.cluster_threshold)
            cluster_ids = cl_result["cluster_ids"]

            # Auto-name clusters using TF-IDF on merged chunk texts
            auto_names = _cluster_mod.auto_name_clusters(merged_texts, cluster_ids)

            for c in range(cl_result["n_clusters"]):
                members = [i for i, ci in enumerate(cluster_ids) if ci == c]
                member_tags = set()
                for i in members:
                    member_tags.update(parsed_tags)
                centroid = cl_result["centroids"][c] if c < len(cl_result["centroids"]) else None
                name = auto_names.get(c, f"Cluster {c}")
                storage.save_cluster(conn, c, name, centroid=centroid,
                                     member_count=len(members), tags=list(member_tags))

            for i, cid in enumerate(chunk_ids):
                storage.update_chunk_cluster(conn, cid, cluster_ids[i] if i < len(cluster_ids) else -1)

            storage.reindex_fts(conn)

        with storage.open_db(db_path) as conn:
            chunks = storage.get_chunks(conn, note_id=note_id)
            clusters = storage.get_clusters(conn)
            tags_rows = storage.list_tags(conn)

        return {
            "note_id": note_id, "path": f"/{filename}",
            "chunks_count": len(chunks), "cluster_count": len(clusters),
            "chunks": chunks, "clusters": clusters,
            "tags": [t["name"] for t in tags_rows],
            "parse_result": parse_result,
        }


class Handler(BaseHTTPRequestHandler):
    pipeline = None
    db_path = ""

    def log_message(self, *a):
        pass

    def _send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, path):
        full = os.path.join(BASE_DIR, path)
        if not os.path.isfile(full):
            self.send_error(404)
            return
        with open(full, encoding="utf-8") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content.encode("utf-8"))))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _send_file(self, relpath):
        full = os.path.join(BASE_DIR, relpath)
        if not os.path.isfile(full):
            self.send_error(404)
            return
        with open(full, "rb") as f:
            content = f.read()
        ct = "application/octet-stream"
        if relpath.endswith(".js"): ct = "application/javascript; charset=utf-8"
        elif relpath.endswith(".css"): ct = "text/css; charset=utf-8"
        elif relpath.endswith(".html"): ct = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _read_body(self):
        ln = int(self.headers.get("Content-Length", 0))
        if ln == 0: return {}
        raw = self.rfile.read(ln)
        return json.loads(raw) if raw else {}

    def do_GET(self):
        p = urlparse(self.path)
        path = p.path
        qs = parse_qs(p.query)

        if path == "/" or path == "/index.html":
            return self._send_html("static/index.html")
        if path.startswith("/static/"):
            return self._send_file(path[1:])

        try:
            if path == "/api/status": return self._api_status()
            if path == "/api/skins": return self._api_skins()
            if path == "/api/clusters": return self._api_clusters()
            if path == "/api/chunks": return self._api_chunks(qs)
            if path == "/api/search": return self._api_search(qs)
            if path == "/api/notes": return self._api_notes(qs)
            if path == "/api/folders": return self._api_folders()
            if path == "/api/tags": return self._api_tags()
            if path == "/api/topology": return self._api_topology()
            # v12 new endpoints
            if path == "/api/documents": return self._api_documents_list()
            if path.startswith("/api/documents/") and path.endswith("/chunks"): return self._api_document_chunks(path)
            if path.startswith("/api/documents/"): return self._api_document_get(path)
            if path == "/api/chunk": return self._api_chunk_detail(qs)
            if path == "/api/graph": return self._api_graph()
            if path == "/api/conflicts": return self._api_conflicts()
            if path == "/api/health": return self._api_health()
        except Exception as e:
            import traceback
            return self._send_json({"error": str(e), "trace": traceback.format_exc()[-1000:]}, 500)

        self.send_error(404)

    def do_POST(self):
        p = urlparse(self.path)
        path = p.path
        try:
            if path == "/api/input": return self._api_input()
            if path == "/api/parse": return self._api_parse()
            if path == "/api/parse_and_save": return self._api_parse_and_save()
            if path == "/api/recluster": return self._api_recluster()
            # v12 new endpoints
            if path == "/api/documents": return self._api_documents_create()
            if path == "/api/chunks": return self._api_chunks_create()
            if path == "/api/chunk_edit": return self._api_chunk_edit()
            if path == "/api/rag": return self._api_rag()
            if path == "/api/consolidate": return self._api_consolidate()
            if path == "/api/conflicts_resolve": return self._api_conflicts_resolve()
        except Exception as e:
            import traceback
            return self._send_json({"error": str(e), "trace": traceback.format_exc()[-1000:]}, 500)
        self.send_error(404)

    def _api_status(self):
        import platform
        mem = "n/a"
        try:
            import psutil
            mem = psutil.virtual_memory().percent
        except: pass
        total_chunks = 0
        total_clusters = 0
        try:
            with _storage_mod.open_db(self.db_path) as conn:
                total_chunks = len(_storage_mod.get_chunks(conn))
                total_clusters = len(_storage_mod.get_clusters(conn))
        except: pass
        self._send_json({
            "ok": True, "pid": os.getpid(), "platform": platform.platform(),
            "memory_percent": mem, "embed_mode": self.pipeline.embed_mode,
            "total_chunks": total_chunks, "total_clusters": total_clusters,
            "time": _now(),
        })

    def _api_skins(self):
        skins = _skinner_mod.list_skins()
        slim = [{"name": s["name"], "kind": s["kind"], "schema": s.get("schema"),
                 "has_js": bool(s.get("source")), "js_length": len(s.get("source") or "")}
                for s in skins]
        self._send_json({"skins": slim})

    def _api_clusters(self):
        with _storage_mod.open_db(self.db_path) as conn:
            clusters = _storage_mod.get_clusters(conn)
        slim = [{"id": c["id"], "name": c["name"], "member_count": c["member_count"],
                 "tags": c.get("tags", []), "metadata": c.get("metadata", {})} for c in clusters]
        self._send_json({"clusters": slim})

    def _api_chunks(self, qs):
        note_id = qs.get("note_id", [None])[0]
        limit = int(qs.get("limit", [50])[0])
        with _storage_mod.open_db(self.db_path) as conn:
            chunks = _storage_mod.get_chunks(conn, note_id=note_id)
        self._send_json({"chunks": chunks[:limit]})

    def _api_search(self, qs):
        q = (qs.get("q", [""])[0] or "").strip()
        engine = qs.get("engine", ["semantic"])[0]
        limit = int(qs.get("limit", [10])[0])
        if not q:
            return self._send_json({"results": [], "query": q})
        with _storage_mod.open_db(self.db_path) as conn:
            if engine == "keyword":
                results = _storage_mod.search_keyword(conn, q, limit)
            else:
                self.pipeline._get_embedder()
                vec = self.pipeline._embedder.embed_query(q)
                results = _storage_mod.search_chunks_semantic(conn, vec, limit)
        self._send_json({"results": results, "query": q, "engine": engine})

    def _api_notes(self, qs):
        folder = qs.get("folder", [None])[0]
        with _storage_mod.open_db(self.db_path) as conn:
            rows = _storage_mod.list_notes(conn, folder=folder)
            notes = []
            for r in rows:
                n = dict(r)
                n["chunks_count"] = len(_storage_mod.get_chunks(conn, note_id=n["id"]))
                notes.append(n)
        self._send_json({"notes": notes})

    def _api_folders(self):
        with _storage_mod.open_db(self.db_path) as conn:
            folders = _storage_mod.list_folders(conn)
        self._send_json({"folders": folders or ["/"]})

    def _api_tags(self):
        with _storage_mod.open_db(self.db_path) as conn:
            tags = _storage_mod.list_tags(conn)
        self._send_json({"tags": tags})

    def _api_topology(self):
        with _storage_mod.open_db(self.db_path) as conn:
            rows = _storage_mod.get_all_chunks_vectors(conn)
            # Get activations
            acts = {}
            for r in rows:
                row = conn.execute("SELECT activation, pinned FROM chunks WHERE id = ?", (r[0],)).fetchone()
                if row:
                    acts[r[0]] = {"activation": row["activation"] or 1.0, "pinned": bool(row["pinned"])}
        if not rows:
            return self._send_json({"points": [], "clusters": []})
        ids = [r[0] for r in rows]
        vecs = [r[1] for r in rows if r[1] is not None]
        payloads = [r[2] for r in rows]
        if not vecs:
            return self._send_json({"points": [], "clusters": []})
        cl = _cluster_mod.cluster_all(vecs, self.pipeline.cluster_threshold, pca_k=3)
        points = []
        for i, cid in enumerate(ids):
            p = payloads[i]
            x2 = cl["pca_2d"][i] if i < len(cl["pca_2d"]) else [0, 0]
            x3 = cl["pca_3d"][i] if i < len(cl["pca_3d"]) else [0, 0, 0]
            act = acts.get(cid, {})
            points.append({
                "chunk_id": cid,
                "cluster": cl["cluster_ids"][i] if i < len(cl["cluster_ids"]) else -1,
                "x2": x2[0], "y2": x2[1],
                "x3": x3[0], "y3": x3[1], "z3": x3[2],
                "text": p["text"][:200], "note_id": p["note_id"],
                "start": p["start"], "end": p["end"],
                "boundary_strength": p["boundary_strength"],
                "tags": p["tags"], "metadata": p["metadata"],
                "activation": act.get("activation", 1.0),
                "pinned": act.get("pinned", False),
            })
        cls = []
        for c in range(cl["n_clusters"]):
            members = [i for i, ci in enumerate(cl["cluster_ids"]) if ci == c]
            member_ids = [ids[i] for i in members]
            cls.append({
                "id": c, "name": f"Cluster {c}",
                "member_count": len(members), "member_ids": member_ids,
                "centroid": cl["centroids"][c] if c < len(cl["centroids"]) else None,
            })
        self._send_json({"points": points, "clusters": cls})

    def _api_input(self):
        body = self._read_body()
        text = (body.get("text") or "").strip()
        if not text:
            return self._send_json({"error": "no text"}, 400)
        if len(text.split()) < 4:
            return self._send_json({"error": "need more text (at least 4 words)"}, 400)
        tags = body.get("tags", [])
        metadata = body.get("metadata", {})
        if not isinstance(tags, list): tags = []
        if not isinstance(metadata, dict): metadata = {}
        result = self.pipeline.run(text, tags=tags, metadata=metadata,
                                   parse=body.get("parse", False))
        self._send_json(result)

    def _api_parse(self):
        body = self._read_body()
        text = (body.get("text") or "").strip()
        if not text:
            return self._send_json({"error": "no text"}, 400)
        result = _llm_parse_mod.parse_text(text, backend=None)
        self._send_json(result)

    def _api_parse_and_save(self):
        body = self._read_body()
        text = (body.get("text") or "").strip()
        path = (body.get("path") or "/parse_test.md").strip()
        if not text:
            return self._send_json({"error": "no text"}, 400)
        result = self.pipeline.run(text, parse=True)
        result["ok"] = True
        result["path"] = path
        result.pop("parse_result", None)
        self._send_json(result)

    def _api_recluster(self):
        body = self._read_body()
        threshold = float(body.get("threshold", 0.75))
        self.pipeline.cluster_threshold = threshold
        # Get all chunks with vectors
        with _storage_mod.open_db(self.db_path) as conn:
            chunks = _storage_mod.get_all_chunks_vectors(conn)
        if not chunks:
            return self._send_json({"ok": True, "n_clusters": 0, "message": "no chunks to cluster"})
        chunk_ids = [r[0] for r in chunks]
        vecs = [r[1] for r in chunks if r[1] is not None]
        texts = [r[2] for r in chunks]
        if not vecs:
            return self._send_json({"ok": True, "n_clusters": 0, "message": "no vectors"})
        # Re-cluster
        cl_result = _cluster_mod.cluster_all(vecs, threshold)
        cluster_ids = cl_result["cluster_ids"]
        # Auto-name
        auto_names = _cluster_mod.auto_name_clusters(texts, cluster_ids)
        # Save
        with _storage_mod.open_db(self.db_path) as conn:
            _storage_mod.clear_clusters(conn)
            for c in range(cl_result["n_clusters"]):
                members = [i for i, ci in enumerate(cluster_ids) if ci == c]
                centroid = cl_result["centroids"][c] if c < len(cl_result["centroids"]) else None
                name = auto_names.get(c, f"Cluster {c}")
                _storage_mod.save_cluster(conn, c, name, centroid=centroid,
                                                member_count=len(members))
            for i, cid in enumerate(chunk_ids):
                _storage_mod.update_chunk_cluster(conn, cid, cluster_ids[i])
            _storage_mod.reindex_fts(conn)
        return self._send_json({"ok": True, "n_clusters": cl_result["n_clusters"], "threshold": threshold})

    # ---------------------------------------------------------------- v12 endpoints

    def _api_documents_list(self):
        with _storage_mod.open_db(self.db_path) as conn:
            docs = [dict(r) for r in conn.execute("SELECT id, path, version, created_at FROM documents ORDER BY updated_at DESC").fetchall()]
        self._send_json({"documents": docs})

    def _api_document_chunks(self, path):
        doc_id = path.split("/api/documents/")[1].split("/chunks")[0]
        with _storage_mod.open_db(self.db_path) as conn:
            chunks = _storage_mod.get_document_chunks(conn, doc_id)
        self._send_json({"chunks": chunks})

    def _api_document_get(self, path):
        doc_id = path.split("/api/documents/")[1]
        with _storage_mod.open_db(self.db_path) as conn:
            doc = _storage_mod.get_document(conn, doc_id)
            if not doc:
                return self._send_json({"error": "not found"}, 404)
            chunks = _storage_mod.get_document_chunks(conn, doc_id)
            doc["chunks"] = chunks
        self._send_json(doc)

    def _api_chunk_get(self, path):
        chunk_id = path.split("/api/chunks/")[1]
        with _storage_mod.open_db(self.db_path) as conn:
            chunk = _storage_mod.get_chunk(conn, chunk_id)
        if not chunk:
            return self._send_json({"error": "not found"}, 404)
        self._send_json(chunk)

    def _api_chunk_detail(self, qs):
        chunk_id = qs.get("chunk_id", [None])[0] or qs.get("id", [None])[0]
        if not chunk_id:
            return self._send_json({"error": "chunk_id required"}, 400)
        with _storage_mod.open_db(self.db_path) as conn:
            chunk = _storage_mod.get_chunk(conn, chunk_id)
        if not chunk:
            return self._send_json({"error": "not found"}, 404)
        self._send_json(chunk)

    def _api_documents_create(self):
        body = self._read_body()
        path = (body.get("path") or "/untitled.md").strip()
        content = body.get("content") or ""
        author = body.get("author", "andrew")
        tenant_id = body.get("tenant_id", "default")
        with _storage_mod.open_db(self.db_path) as conn:
            did = _storage_mod.save_document(conn, path, content, author, tenant_id)
            doc = _storage_mod.get_document(conn, did)
        self._send_json(doc)

    def _api_chunks_create(self):
        body = self._read_body()
        text = (body.get("text") or "").strip()
        if not text:
            return self._send_json({"error": "no text"}, 400)
        source_doc_id = body.get("source_doc_id")
        with _storage_mod.open_db(self.db_path) as conn:
            import hashlib
            cid = f"c{hashlib.sha256(text.encode()).hexdigest()[:17]}"
            conn.execute(
                "INSERT OR REPLACE INTO chunks (id, text, note_id, source_doc_id, created, start, end) VALUES (?,?,?,?,?,?,?)",
                (cid, text, body.get("note_id", "native"), source_doc_id, _now(), 0, 0)
            )
        self._send_json({"id": cid, "text": text})

    def _api_chunk_edit(self):
        body = self._read_body()
        chunk_id = body.get("chunk_id")
        new_text = body.get("new_text")
        if not chunk_id or new_text is None:
            return self._send_json({"error": "chunk_id and new_text required"}, 400)
        with _storage_mod.open_db(self.db_path) as conn:
            result = _storage_mod.chunk_to_document_sync(conn, chunk_id, new_text)
        self._send_json({"ok": result})

    def _api_graph(self):
        with _storage_mod.open_db(self.db_path) as conn:
            chunks = [dict(r) for r in conn.execute("SELECT id, text, activation, cluster, pos_x, pos_y, pos_z FROM chunks").fetchall()]
            links = [dict(r) for r in conn.execute("SELECT source_chunk_id, target_chunk_id, link_type, weight FROM links_v2").fetchall()]
        self._send_json({"nodes": chunks, "edges": links})

    def _api_conflicts(self):
        with _storage_mod.open_db(self.db_path) as conn:
            conflicts = [dict(r) for r in conn.execute("SELECT * FROM conflicts ORDER BY detected_at DESC").fetchall()]
        self._send_json({"conflicts": conflicts})

    def _api_conflicts_resolve(self):
        body = self._read_body()
        conflict_id = body.get("conflict_id")
        resolution = body.get("resolution", "kept_both")
        if not conflict_id:
            return self._send_json({"error": "conflict_id required"}, 400)
        with _storage_mod.open_db(self.db_path) as conn:
            conn.execute(
                "UPDATE conflicts SET resolved=1, resolution=?, resolved_at=? WHERE id=?",
                (resolution, _now(), conflict_id)
            )
        self._send_json({"ok": True})

    def _api_rag(self):
        body = self._read_body()
        query = (body.get("query") or "").strip()
        if not query:
            return self._send_json({"error": "no query"}, 400)
        limit = int(body.get("limit", 5))
        vec = self.pipeline._embedder.embed_query(query)
        with _storage_mod.open_db(self.db_path) as conn:
            results = _storage_mod.search_chunks_semantic(conn, vec, limit=limit)
            for r in results:
                _storage_mod.record_chunk_access(conn, r["chunk_id"])
        self._send_json({"query": query, "results": results})

    def _api_consolidate(self):
        with _storage_mod.open_db(self.db_path) as conn:
            _storage_mod.decay_activations(conn, 0.02)
            _storage_mod.decay_links(conn, 0.01)
            hot = _storage_mod.get_hot_chunks(conn, 20)
            for chunk in hot:
                if chunk["activation"] > 0.5:
                    _storage_mod.log_dynamics(conn, chunk["id"], "reinforce", chunk["activation"], min(1.0, chunk["activation"] + 0.05))
        self._send_json({"ok": True, "message": "consolidation tick complete"})

    def _api_health(self):
        with _storage_mod.open_db(self.db_path) as conn:
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            link_count = conn.execute("SELECT COUNT(*) FROM links_v2").fetchone()[0]
            conflict_count = conn.execute("SELECT COUNT(*) FROM conflicts WHERE resolved=0").fetchone()[0]
            doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        self._send_json({
            "ok": True,
            "version": "v12",
            "chunks": chunk_count,
            "links": link_count,
            "conflicts": conflict_count,
            "documents": doc_count,
        })


class ReusableThreadingTCPServer(ThreadingTCPServer):
    allow_reuse_address = True


def main(port=8779, db_path=None, vault_path=None, embed="miniml", cluster_threshold=0.75):
    global _db_path
    parser = argparse.ArgumentParser(description="Signum v11")
    parser.add_argument("--port", type=int, default=port)
    parser.add_argument("--db", default=db_path or os.path.join(BASE_DIR, "data", "signum.db"))
    parser.add_argument("--vault", default=vault_path or os.path.join(BASE_DIR, "data", "vault"))
    parser.add_argument("--embed", default=embed, choices=["miniml", "bge", "nomic"])
    parser.add_argument("--cluster-threshold", type=float, default=cluster_threshold)
    args = parser.parse_args()

    _db_path = os.path.abspath(args.db)
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
    os.makedirs(args.vault, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "data", "skins"), exist_ok=True)

    _import_all()
    with _storage_mod.open_db(_db_path) as conn:
        _storage_mod.reindex_fts(conn)
        _storage_mod.migrate_v11_to_v12(conn)

    pipeline = Pipeline(_db_path, embed_mode=args.embed, cluster_threshold=args.cluster_threshold)
    Handler.pipeline = pipeline
    Handler.db_path = _db_path

    server = ReusableThreadingTCPServer(("127.0.0.1", args.port), Handler)
    print(f"[signum v11] http://127.0.0.1:{args.port}/", flush=True)
    print(f"  db: {_db_path}", flush=True)
    print(f"  embed: {args.embed}", flush=True)
    print(f"  cluster threshold: {args.cluster_threshold}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[stopped]", flush=True)


if __name__ == "__main__":
    main()
