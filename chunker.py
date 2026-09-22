"""v11 Meaning Chunker — extracted and cleaned from meaning_server_v9.py.

Three scans (structure, linguistic, meaning sweep), one combined timeline,
Otsu cut line, local-peak split, tiny-piece merge.

No hardcoded behavioral thresholds — cut line comes from the data (Otsu).
Safety floors only: MIN_WIN, MAX_WIN, MIN_PIECE.

Design change from v9: embedder is injected via embed_fn, not loaded here.
The embedder lives in embedder.py. The chunker produces candidate positions;
vectors come from outside.
"""
from __future__ import annotations
import re
import difflib
from typing import List, Dict, Any, Optional, Callable, Tuple

import numpy as np

# ---------------------------------------------------------------- safety floors

MIN_WIN = 4          # smallest allowed sweep window (words)
MAX_WIN = 30         # largest allowed sweep window
MIN_PIECE = 2        # a chunk may not be smaller than this many words

TURN_WORDS_EN = [
    "however", "but then", "anyway", "anyways", "meanwhile",
    "afterwards", "later", "next", "suddenly", "finally",
    "in conclusion", "on the other hand", "by the way", "speaking of",
]
TURN_WORDS_ID = [
    "tapi", "namun", "kemudian", "lalu", "sedangkan", "ngomong-ngomong",
    "btw", "gimana-gimana", "akhirnya", "terus",
]

PUNCT_RE = re.compile(r"[.!?\u3002\uff01\uff1f;]$")
PARA_RE = re.compile(r"\n\s*\n|\n")


# ---------------------------------------------------------------- units


def split_sentences(text: str) -> Tuple[List[Dict[str, Any]], List[int], int]:
    """Return (sents, para_starts, word_count).

    sents: list of {start, end, text} word-index ranges.
    para_starts: first-word index of each paragraph after the first.
    """
    sents: List[Dict[str, Any]] = []
    start_w = 0
    for para_i, para in enumerate(PARA_RE.split(text)):
        words = para.split()
        if not words:
            continue
        buf: List[str] = []
        buf_start = start_w
        for w in words:
            buf.append(w)
            if PUNCT_RE.search(w):
                sents.append({"start": buf_start, "end": start_w + 1, "text": " ".join(buf)})
                buf, buf_start = [], start_w + 1
            start_w += 1
        if buf:
            sents.append({"start": buf_start, "end": start_w, "text": " ".join(buf)})
        if para_i > 0:
            pass  # para_starts computed below
    # paragraph break positions
    wcount = 0
    paras = [p for p in PARA_RE.split(text) if p.split()]
    para_starts: List[int] = []
    for p in paras:
        para_starts.append(wcount)
        wcount += len(p.split())
    return sents, para_starts[1:], len(text.split())


# ---------------------------------------------------------------- scans


def derive_window(sent_bounds: List[Dict[str, Any]]) -> int:
    """Window width from THIS text's own rhythm: median sentence length."""
    lens = [s["end"] - s["start"] for s in sent_bounds] or [10]
    med = int(np.median(lens))
    return max(MIN_WIN, min(MAX_WIN, med))


def scan_structure(
    words: List[str],
    sent_bounds: List[Dict[str, Any]],
    para_starts: List[int],
    embed_fn: Callable[[List[str]], List[List[float]]],
    tag_signals: Optional[Dict[str, List[int]]] = None,
) -> List[Dict[str, Any]]:
    """Structure marks (punctuation + paragraph breaks + tag signals).

    Each mark gets sign-to-sign cosine: mean(left side) vs mean(right side).
    """
    n = len(words)
    marks: set[int] = set()
    for i, w in enumerate(words[:-1]):
        if PUNCT_RE.search(w):
            marks.add(i + 1)
    marks.update(para_starts)
    if tag_signals:
        for positions in tag_signals.values():
            for p in positions:
                if MIN_PIECE <= p <= n - MIN_PIECE:
                    marks.add(int(p))

    marks = sorted(m for m in marks if MIN_PIECE <= m <= n - MIN_PIECE)
    if not marks:
        return []

    W = derive_window(sent_bounds if sent_bounds else [{"start": 0, "end": n}])
    vecs = embed_fn(words)

    out: List[Dict[str, Any]] = []
    para_set = set(para_starts)
    for m in marks:
        lo, hi = max(0, m - W), min(n, m + W)
        lv = _mean(vecs[lo:m])
        rv = _mean(vecs[m:hi])
        kind: str
        if m in para_set:
            kind = "paragraph"
        elif tag_signals and any(m in ps for ps in tag_signals.values()):
            kind = "tag"
        else:
            kind = "punctuation"
        out.append({"pos": m, "strength": round(1 - _cos(lv, rv), 4), "kind": kind})
    return out


def scan_linguistic(
    words: List[str],
    embed_fn: Callable[[List[str]], List[List[float]]],
) -> List[Dict[str, Any]]:
    """Fuzzy turn-word hits; sign-to-sign cosine around each."""
    n = len(words)
    low = [w.lower().strip(".,!?;:") for w in words]
    out: List[Dict[str, Any]] = []
    checked: set[int] = set()
    for tw in TURN_WORDS_EN + TURN_WORDS_ID:
        for i, w in enumerate(low):
            hit: Optional[int] = None
            if w == tw:
                hit = i
            elif abs(len(w) - len(tw)) <= 2 and difflib.SequenceMatcher(None, w, tw).ratio() > 0.8:
                hit = i
            if hit is None or hit in checked or hit < MIN_PIECE or hit > n - MIN_PIECE:
                continue
            checked.add(hit)
            lw = words[max(0, hit - MIN_WIN):hit]
            rw = words[hit:hit + MIN_WIN]
            if not lw or not rw:
                continue
            lv = _mean(embed_fn(lw))
            rv = _mean(embed_fn(rw))
            out.append({"pos": hit, "strength": round(1 - _cos(lv, rv), 4), "kind": f"turnword:{tw}"})
    return sorted(out, key=lambda d: d["pos"])


def scan_meaning(
    words: List[str],
    walls: List[Dict[str, Any]],
    embed_fn: Callable[[List[str]], List[List[float]]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Sign-to-sign sweep between walls: prev window vs after window at every gap.

    walls: structure marks that are paragraphs (already scored).
    """
    n = len(words)
    W = derive_window([{"start": 0, "end": max(1, n // 4)}])
    wallset = {m["pos"] for m in walls}
    vecs = embed_fn(words)
    out: List[Dict[str, Any]] = []
    for g in range(1, n):
        if g in wallset:
            continue
        lw = words[max(0, g - W):g]
        rw = words[g:min(n, g + W)]
        if len(lw) < MIN_WIN or len(rw) < MIN_WIN:
            continue
        lv = _mean(vecs[max(0, g - W):g])
        rv = _mean(vecs[g:min(n, g + W)])
        out.append({"pos": g, "strength": round(1 - _cos(lv, rv), 4)})
    return out, W


# ---------------------------------------------------------------- math helpers


def _cos(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _mean(vs: List[List[float]]) -> List[float]:
    if not vs:
        return [0.0]
    arr = np.asarray(vs, dtype=float)
    return arr.mean(axis=0).tolist()


# ---------------------------------------------------------------- combine


def combine(
    struct_marks: List[Dict[str, Any]],
    ling_marks: List[Dict[str, Any]],
    sweep: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge all scans by position into one timeline.

    Agreement boost: when two scans agree on the same spot, +0.1 per extra kind.
    """
    timeline: Dict[int, Dict[str, Any]] = {}
    for m in struct_marks + ling_marks:
        p = m["pos"]
        if p not in timeline:
            timeline[p] = {"pos": p, "strength": 0.0, "kinds": []}
        timeline[p]["kinds"].append(m["kind"])
        timeline[p]["strength"] = max(timeline[p]["strength"], m["strength"])

    # agreement boost
    for p, e in timeline.items():
        kinds = set(e["kinds"])
        if len(kinds) > 1:
            e["strength"] = min(1.0, e["strength"] + 0.1 * (len(kinds) - 1))
            e["agreement"] = True

    for s in sweep:
        p = s["pos"]
        if p in timeline:
            timeline[p]["strength"] = max(timeline[p]["strength"], s["strength"])
        else:
            timeline[p] = {"pos": p, "strength": s["strength"], "kinds": ["sweep"]}
    return sorted(timeline.values(), key=lambda d: d["pos"])


# ---------------------------------------------------------------- split


def otsu(values: List[float]) -> float:
    vals = np.asarray([v for v in values if v is not None], dtype=float)
    if len(vals) < 2:
        return float("inf")
    hist, edges = np.histogram(vals, bins=min(16, len(vals)))
    best_t, best_var = edges[0], -1.0
    total = vals.size
    for i in range(1, len(hist)):
        w0 = hist[:i].sum() / total
        w1 = 1 - w0
        if w0 == 0 or w1 == 0:
            continue
        c0 = vals[vals <= edges[i]]
        c1 = vals[vals > edges[i]]
        v = w0 * c0.var() + w1 * c1.var()
        if best_var < 0 or v < best_var:
            best_var, best_t = v, edges[i]
    return float(best_t)


def split(
    candidates: List[Dict[str, Any]], n_words: int, cut_line: float
) -> Tuple[List[int], List[Dict[str, Any]]]:
    """Cut only at LOCAL PEAKS above the line, merge tiny trailing pieces."""
    by_pos = {c["pos"]: c["strength"] for c in candidates}
    cuts: List[int] = []
    for c in candidates:
        p = c["pos"]
        if p < MIN_PIECE or p > n_words - MIN_PIECE or c["strength"] < cut_line:
            continue
        left = max(by_pos.get(q, 0) for q in range(p - 3, p))
        right = max(by_pos.get(q, 0) for q in range(p + 1, p + 4))
        if c["strength"] >= left and c["strength"] > right:
            cuts.append(p)
    bounds = [0] + sorted(cuts) + [n_words]
    chunks: List[Dict[str, Any]] = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b - a == 0:
            continue
        if chunks and b - a < MIN_PIECE:
            chunks[-1]["end"] = b
            continue
        chunks.append({"start": a, "end": b})
    return cuts, chunks


# ---------------------------------------------------------------- public API


def chunk_text(
    text: str,
    embed_fn: Callable[[List[str]], List[List[float]]],
    tag_signals: Optional[Dict[str, List[int]]] = None,
) -> Dict[str, Any]:
    """Full scan → combine → split pipeline.

    Returns:
        {
            "words": list[str],
            "window": int,
            "cut_line": float,
            "signposts": list[{pos, strength, kind}],
            "fragments": list[{start, end, text, boundary_strength}],
        }
    """
    text = text.strip()
    if not text:
        return {"words": [], "window": 0, "cut_line": float("inf"),
                "signposts": [], "fragments": []}

    words = text.split()
    n = len(words)
    if n < MIN_PIECE * 2:
        return {
            "words": words,
            "window": 0,
            "cut_line": float("inf"),
            "signposts": [],
            "fragments": [{"start": 0, "end": n, "text": text,
                            "boundary_strength": 0.0}],
        }

    sents, para_starts, _ = split_sentences(text)
    struct = scan_structure(words, sents, para_starts, embed_fn, tag_signals)
    ling = scan_linguistic(words, embed_fn)
    walls = [m for m in struct if m["kind"] == "paragraph"]
    sweep, W = scan_meaning(words, walls, embed_fn)

    candidates = combine(struct, ling, sweep)
    strengths = [c["strength"] for c in candidates]
    cut_line = otsu(strengths)
    cuts, frags = split(candidates, n, cut_line)

    out_frags = []
    for i, ch in enumerate(frags):
        bs = next((c["strength"] for c in candidates if c["pos"] == ch["end"]), 0.0)
        out_frags.append({
            "start": ch["start"],
            "end": ch["end"],
            "text": " ".join(words[ch["start"]:ch["end"]]),
            "boundary_strength": round(bs, 4),
        })

    return {
        "words": words,
        "window": W,
        "cut_line": round(cut_line, 4),
        "signposts": candidates,
        "fragments": out_frags,
    }
