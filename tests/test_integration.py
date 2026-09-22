"""v11 Integration test — the MVP-ships proof.

Starts the server, sends input with a wikilink, verifies:
  - chunks produced
  - wikilink splice merges fragments
  - clusters formed
  - 4 built-in skins present
  - semantic search returns results
  - chunk/move endpoint works
  - parse + parse_and_save work
"""
from __future__ import annotations
import os
import sys
import json
import time
import threading
import urllib.request
import urllib.error
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PORT = 18999
BASE = f"http://127.0.0.1:{PORT}"


def request(method, path, body=None, timeout=60):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read()
        return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw.decode("utf-8", "replace")[:500]}
    except Exception as e:
        return None, {"error": str(e)}


def wait_for_status(timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            code, data = request("GET", "/api/status")
            if code == 200 and data.get("ok"):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def test():
    failures = []

    # 1. server reports ok
    if not wait_for_status(45):
        failures.append("server did not become ready in 45s")
        return failures
    code, status = request("GET", "/api/status")
    if code != 200 or not status.get("ok"):
        failures.append(f"/api/status not ok: {status}")
        return failures
    print(f"OK /api/status: {status}")

    # 2. skins present
    code, skins = request("GET", "/api/skins")
    if code != 200:
        failures.append(f"/api/skins failed: {code} {skins}")
    else:
        skin_names = [s["name"] for s in skins.get("skins", [])]
        for want in ["city", "forest", "village", "planet"]:
            if want not in skin_names:
                failures.append(f"skin missing: {want} (have {skin_names})")
        print(f"OK /api/skins: {len(skin_names)} skins, names={skin_names}")
        city = next((s for s in skins["skins"] if s["name"] == "city"), None)
        if city and city.get("js_length", 0) > 100:
            print(f"OK city skin has JS ({city['js_length']} chars)")
        else:
            failures.append("city skin JS missing/short")

    # 3. input with wikilink -> chunks + splice + clusters
    text = ("The church planted a new community center in Jakarta. "
            "[[Jakarta]] families now use it for free English classes. "
            "The youth program meets every Saturday. "
            "Indonesian nationalism grew strongly after 1945. "
            "[[Nationalism]] shaped the youth movement and local language pride. "
            "Vector databases store number-lists and answer nearest-neighbor queries.")
    code, data = request("POST", "/api/input", {
        "text": text,
        "mode": "textbox",
        "tags": ["church", "jakarta", "youth"],
        "metadata": {"location": "Jakarta", "topic": "outreach"},
    }, timeout=90)
    if code != 200:
        failures.append(f"/api/input failed: {code} {data}")
        return failures
    print(f"OK /api/input: {data.get('chunks_count')} chunks, {data.get('cluster_count')} clusters")
    if data.get("chunks_count", 0) < 1:
        failures.append("/api/input produced no chunks")
    if data.get("cluster_count", 0) < 1:
        failures.append("/api/input produced no clusters")
    if "error" in data:
        failures.append(f"/api/input returned error: {data['error']}")

    # wikilink splice sanity: a short text with 2 wikilinks should produce
    # fewer chunks than a naive per-sentence splitter would.
    nc = data.get("chunks_count", 0)
    if nc > 10:
        failures.append(f"splice may not be working: {nc} chunks for a short text (expected fewer)")

    # 4. semantic search
    code, search = request("GET", "/api/search?q=Jakarta&engine=semantic&limit=5")
    if code != 200:
        failures.append(f"/api/search failed: {code} {search}")
    else:
        results = search.get("results", [])
        print(f"OK /api/search: {len(results)} results for 'Jakarta'")
        if len(results) < 1:
            failures.append("/api/search returned no results for 'Jakarta'")
        else:
            top = results[0]
            print(f"  top: sim={top.get('similarity')} text={top.get('text','')[:60]!r}")

    # 5. clusters
    code, clusters = request("GET", "/api/clusters")
    if code != 200:
        failures.append(f"/api/clusters failed: {code} {clusters}")
    else:
        cl = clusters.get("clusters", [])
        print(f"OK /api/clusters: {len(cl)} clusters")
        if len(cl) < 1:
            failures.append("/api/clusters returned no clusters")
        for c in cl[:3]:
            print(f"  cluster {c.get('id')}: name={c.get('name')!r} members={c.get('member_count')} "
                  f"tags={c.get('tags')} centroid_dim={len(c.get('centroid') or [])}")

    # 6. chunk/move
    if data.get("chunks"):
        cid = data["chunks"][0]["id"]
        code, moved = request("POST", "/api/chunks/move", {
            "chunk_id": cid,
            "new_start": data["chunks"][0]["start"] + 0,
            "new_end": data["chunks"][0]["end"],
            "reembed": False,
        })
        if code != 200:
            failures.append(f"/api/chunks/move failed: {code} {moved}")
        else:
            print(f"OK /api/chunks/move: {moved}")

    # 7. parse
    code, parsed = request("POST", "/api/parse", {
        "text": "Meeting with Ibu Yanti on 2026-09-18 about the [[budget]]. Budget: 2.1 million. #finance #jakarta"
    })
    if code != 200:
        failures.append(f"/api/parse failed: {code} {parsed}")
    else:
        print(f"OK /api/parse: tags={parsed.get('tags')} metadata_keys={list(parsed.get('metadata', {}).keys())}")
        if "person_yanti" not in parsed.get("tags", []):
            failures.append("parse didn't extract 'person_yanti' tag")
        if "budget" not in parsed.get("tags", []):
            failures.append("parse didn't extract 'budget' tag")
        if "date" not in parsed.get("metadata", {}):
            failures.append("parse didn't extract date metadata")

    # 8. parse_and_save
    code, saved = request("POST", "/api/parse_and_save", {
        "text": "Test note from integration test. [[TestTag]] #integrationtest",
        "path": "/integration_test.md",
    })
    if code != 200:
        failures.append(f"/api/parse_and_save failed: {code} {saved}")
    else:
        print(f"OK /api/parse_and_save: note={saved.get('path')} chunks={saved.get('chunks_count')} tags={saved.get('tags')}")
    if saved.get('chunks_count', 0) < 1:
        failures.append('/api/parse_and_save produced no chunks')

    return failures


def server_main(port):
    import server as srv
    srv.main(port)


def main():
    print("starting server thread...", flush=True)
    t = threading.Thread(target=server_main, args=(PORT,), daemon=True)
    t.start()

    print("waiting for server to come up...", flush=True)
    ok = wait_for_status(45)
    if not ok:
        print("FATAL: server did not start", flush=True)
        sys.exit(2)

    print("running integration tests...", flush=True)
    failures = test()

    if failures:
        print("\nFAILURES:", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        sys.exit(1)
    else:
        print("\nALL INTEGRATION TESTS PASSED", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
