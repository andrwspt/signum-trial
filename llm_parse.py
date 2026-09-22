"""v11 LLM Parse — extract tags/metadata/structure from text.

Two modes:
  - rules  (default, always works, no LLM needed)
  - api    (optional: user provides an LLM API callable)

The parse result feeds storage: tags go to the tags table + note.tags field,
metadata goes to note.metadata. For MVP, parsing happens at note level and
applies to the note + all its chunks.
"""
from __future__ import annotations
import re
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------- patterns

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")
KV_RE = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_.\s]*?):\s*"
    r"(?P<val>[^\n,;]+?)(?=\s*,?\s*(?:[A-Za-z_][A-Za-z0-9_.\s]*?:|$))",
    re.IGNORECASE | re.MULTILINE,
)
KV_RE2 = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_.\s]*?)\s*=\s*"
    r"(?P<val>[^\n,;]+?)(?=\s*,?\s*(?:[A-Za-z_][A-Za-z0-9_.\s]*?\s*=|$))",
    re.IGNORECASE | re.MULTILINE,
)
DATE_RE = re.compile(
    r"\b(?P<date>"
    r"\d{4}-\d{2}-\d{2}"
    r"|"
    r"\d{1,2}/\d{1,2}/\d{2,4}"
    r"|"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r")\b",
    re.IGNORECASE,
)
NUMERIC_RE = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_\s]*?)\s*"
    r"(?P<val>"
    r"\d+(?:\.\d+)?\s*(?:million|billion|thousand|hundred|k|M|B|T|million rupiah|rupiah|USD|$)"
    r"|\d+(?:\.\d+)?)"
    r"\s*$",
    re.IGNORECASE,
)
NAME_RE = re.compile(
    r"\b(?:Ibu|Bapak|Pak|Bu|Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
)


def _first(pattern, text, group="val"):
    m = pattern.search(text)
    if not m:
        return None
    return (m.group(group) or "").strip()


def _all(pattern, text, group="val"):
    return [m.group(group).strip() for m in pattern.finditer(text) if m.group(group)]


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


# ---------------------------------------------------------------- rules parser


def parse_rules(text: str) -> Dict[str, Any]:
    """Rule-based extraction. Always works, no LLM."""
    tags: set = set()
    metadata: Dict[str, Any] = {}

    # wikilinks -> tags
    for m in WIKILINK_RE.finditer(text):
        term = m.group(1).strip()
        if term:
            tags.add(_slug(term))

    # hashtags -> tags
    for m in HASHTAG_RE.finditer(text):
        tags.add(_slug(m.group(1)))

    # keapaanaan-style "tag: value" or "tag = value"
    for m in KV_RE.finditer(text):
        key = _slug(m.group("key"))
        val = m.group("val").strip().rstrip(",").strip()
        if key and val:
            metadata[key] = val
    for m in KV_RE2.finditer(text):
        key = _slug(m.group("key"))
        val = m.group("val").strip().rstrip(",").strip()
        if key and val and key not in metadata:
            metadata[key] = val

    # dates
    for m in DATE_RE.finditer(text):
        metadata["date"] = m.group("date")

    # people (Indonesian honorifics + English)
    for m in NAME_RE.finditer(text):
        name = m.group(1).strip()
        if name:
            tags.add("person_" + _slug(name))
            metadata.setdefault("people", []).append(name)

    # numeric amounts
    for m in NUMERIC_RE.finditer(text):
        key = _slug(m.group("key"))
        val = m.group("val").strip()
        if key and val:
            metadata[key] = val

    # capitalized phrases of 2+ words -> candidate topics
    caps = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    for phrase in caps:
        phrase = phrase.strip()
        if len(phrase) > 10 and phrase not in ("The Church", "The Youth", "The Community"):
            tags.add(_slug(phrase))

    # first sentence as summary
    sents = re.split(r"[.!?\n]\s+", text)
    summary = sents[0].strip() if sents else text.strip()
    if summary and len(summary) > 120:
        summary = summary[:117] + "..."

    return {
        "tags": sorted(tags),
        "metadata": metadata,
        "summary": summary,
        "structure": {"first_sentence": summary},
    }


# ---------------------------------------------------------------- API parser


def parse_api(text: str, backend: Callable[[str], Dict[str, Any]]) -> Dict[str, Any]:
    """Delegate to an LLM backend callable. Falls back to rules on failure."""
    try:
        result = backend(text)
        if not isinstance(result, dict):
            raise ValueError("backend must return a dict")
        tags = result.get("tags") or []
        metadata = result.get("metadata") or {}
        if not isinstance(tags, list):
            tags = [tags] if tags else []
        if not isinstance(metadata, dict):
            metadata = {}
        summary = result.get("summary") or ""
        if not isinstance(summary, str):
            summary = ""
        structure = result.get("structure") or {}
        if not isinstance(structure, dict):
            structure = {}
        return {
            "tags": [str(t).strip() for t in tags if str(t).strip()],
            "metadata": {str(k): v for k, v in metadata.items()},
            "summary": str(summary).strip(),
            "structure": structure,
            "backend": "api",
        }
    except Exception:
        return parse_rules(text)


# ---------------------------------------------------------------- public API


def parse_text(
    text: str,
    backend: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Parse text into tags/metadata/structure/summary.

    Args:
        text: the text to parse.
        backend: optional LLM callable. If None, uses rules only.

    Returns:
        {"tags": list[str], "metadata": dict, "summary": str, "structure": dict}
    """
    if not text or not text.strip():
        return {"tags": [], "metadata": {}, "summary": "", "structure": {}}
    if backend is not None:
        return parse_api(text, backend)
    return parse_rules(text)
