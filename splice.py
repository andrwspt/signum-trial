"""v11 Wikilink Splice.

Takes fragments from chunker.chunk_text (which may be over-cut by Otsu)
and merges adjacent fragments back when signals say they're one thought.

Three signals, in priority order:
  1. Wikilink shared across boundary — [[term]] in one fragment, term
     mentioned in the other. Strongest signal. Author's own navigraph.
  2. Very high cross-fragment cosine (> 0.92) — re-merge only when the
     split clearly over-cut (similarity so high the cut was wrong).
  3. No strong structural boundary between them — no paragraph break, no
     sentence-ending punctuation in the gap.

Order: chunker → embedder → splice. Splice needs fragment vectors.
"""
from __future__ import annotations
import re
from typing import List, Dict, Any, Optional, Set, Tuple
import json

import numpy as np

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
PUNCT_RE = re.compile(r"[.!?\u3002\uff01\uff1f;]$")
COS_HIGH = 0.92  # only re-merge on very high similarity (avoid undoing split)


# ---------------------------------------------------------------- helpers


def wikilinks_in(text: str) -> Set[str]:
    """Set of [[term]] terms (lowercased, stripped)."""
    return {m.group(1).strip().lower() for m in WIKILINK_RE.finditer(text)}


def mentioned_terms(text: str) -> Set[str]:
    """Set of lowercase words in text (stripped of punctuation)."""
    out: Set[str] = set()
    for w in text.split():
        clean = w.strip(".,!?;:()[]{}<>\"'").lower()
        if clean and len(clean) > 1:
            out.add(clean)
    return out


def _cos(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    if a is None or b is None or not a or not b:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _mean_vecs(vecs: List[Optional[List[float]]]) -> Optional[List[float]]:
    vals = [v for v in vecs if v is not None]
    if not vals:
        return None
    arr = np.asarray(vals, dtype=float)
    return arr.mean(axis=0).tolist()


# ---------------------------------------------------------------- signals


def has_wikilink_signal(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    """Wikilink in left, term mentioned in right (or vice versa)."""
    ll = wikilinks_in(left["text"])
    lr = mentioned_terms(left["text"])
    rl = wikilinks_in(right["text"])
    rr = mentioned_terms(right["text"])
    # [[term]] in left, term mentioned in right
    if ll & rr:
        return True
    # [[term]] in right, term mentioned in left
    if rl & lr:
        return True
    # [[same term]] in both
    if ll & rl:
        return True
    return False


def has_high_similarity(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    lv = left.get("vector")
    rv = right.get("vector")
    return _cos(lv, rv) > COS_HIGH


def has_no_boundary(left: Dict[str, Any], right: Dict[str, Any],
                    words: List[str]) -> bool:
    """True if no paragraph break and no sentence-ending punctuation between them."""
    a, b = left["end"], right["start"]
    if a >= b:
        return False
    # check words in the gap (a .. b-1) for punctuation or paragraph
    for i in range(a, b):
        if i < len(words) and PUNCT_RE.search(words[i]):
            return False
    return True


# ---------------------------------------------------------------- merge


def merge_frags(
    left: Dict[str, Any],
    right: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge two adjacent fragments into one."""
    new_vec = None
    lv = left.get("vector")
    rv = right.get("vector")
    if lv is not None or rv is not None:
        new_vec = _mean_vecs([lv, rv])
    return {
        "start": left["start"],
        "end": right["end"],
        "text": (left["text"] + " " + right["text"]).strip(),
        "vector": new_vec,
        "tags": _merge_lists(left.get("tags", []), right.get("tags", [])),
        "metadata": _merge_dicts(left.get("metadata", {}), right.get("metadata", {})),
        "boundary_strength": min(left.get("boundary_strength", 0.0),
                                 right.get("boundary_strength", 0.0)),
        "source": "splice",
        "cluster": -1,
    }


def _merge_lists(a: Any, b: Any) -> List[Any]:
    out: List[Any] = []
    seen: set = set()
    for x in list(a or []) + list(b or []):
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _merge_dicts(a: Any, b: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    d.update(a or {})
    d.update(b or {})
    return d


# ---------------------------------------------------------------- main


def splice(
    fragments: List[Dict[str, Any]],
    words: List[str],
) -> List[Dict[str, Any]]:
    """Run the splice pass over fragments.

    Returns merged fragments (fewer than or equal to input).
    """
    if len(fragments) <= 1:
        return list(fragments)

    merged: List[Dict[str, Any]] = []
    i = 0
    while i < len(fragments):
        current = dict(fragments[i])
        j = i + 1
        while j < len(fragments):
            nxt = fragments[j]
            # signal 1 — wikilink
            if has_wikilink_signal(current, nxt):
                current = merge_frags(current, nxt)
                j += 1
                continue
            # signal 2 — very high similarity
            if has_high_similarity(current, nxt):
                current = merge_frags(current, nxt)
                j += 1
                continue
            # signal 3 — no structural boundary
            if has_no_boundary(current, nxt, words):
                current = merge_frags(current, nxt)
                j += 1
                continue
            break
        merged.append(current)
        i = j
    return merged


def extract_links_from_fragments(fragments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a wikilink graph from fragments: source_index → target_term.

    Returns list of {source_idx, target_term, target_idx_or_none}.
    """
    links: List[Dict[str, Any]] = []
    term_to_frags: Dict[str, List[int]] = {}
    for i, f in enumerate(fragments):
        for term in wikilinks_in(f["text"]):
            term_to_frags.setdefault(term, []).append(i)
    for term, src_idxs in term_to_frags.items():
        for si in src_idxs:
            # find other fragments that mention this term
            for ti, f in enumerate(fragments):
                if ti == si:
                    continue
                if term in mentioned_terms(f["text"]):
                    links.append({
                        "source_idx": si,
                        "target_term": term,
                        "target_idx": ti,
                    })
    return links


def build_links_for_storage(
    fragments: List[Dict[str, Any]],
    chunk_ids: List[str],
) -> List[Dict[str, Any]]:
    """Convert fragment-level links to storage links (chunk ids).

    Returns list of {source_chunk_id, target_chunk_id, link_term}.
    """
    frag_links = extract_links_from_fragments(fragments)
    out: List[Dict[str, Any]] = []
    idx_to_id = {i: cid for i, cid in enumerate(chunk_ids)}
    for lk in frag_links:
        si = lk["source_idx"]
        ti = lk["target_idx"]
        if si not in idx_to_id or ti not in idx_to_id:
            continue
        out.append({
            "source_chunk_id": idx_to_id[si],
            "target_chunk_id": idx_to_id[ti],
            "link_term": lk["target_term"],
        })
    # dedupe
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for lk in out:
        key = (lk["source_chunk_id"], lk["target_chunk_id"], lk["link_term"])
        if key not in seen:
            seen.add(key)
            deduped.append(lk)
    return deduped
