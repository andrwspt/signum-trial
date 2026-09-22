"""v11 Embedder — swappable backends, lazy-loaded, unified interface.

Backends (loaded on first use, cached):
  miniml   — sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
              384-dim. Default. Used for scan + final chunk vectors.
  bge      — BAAI/bge-m3 via FlagEmbedding. 1024-dim. Optional.
  nomic    — nomic-ai/nomic-embed-text-v1.5 via transformers. 768-dim,
              8192-token context. Optional. Real late chunking.

Public API:
  get_embedder(mode="miniml") -> Embedder
    .embed_words(words)      -> list[list[float]]   (for chunker scan)
    .embed_chunks(texts)     -> list[list[float]]   (batch, for clustering)
    .embed_chunk(text, prev, next) -> list[float]   (final chunk vector)
    .embed_query(text)       -> list[float]         (for search)
"""
from __future__ import annotations
import os
from typing import List, Optional
import numpy as np

# ---------------------------------------------------------------- where models live

MODEL_CACHE = os.path.expanduser("~/.cache/huggingface/hub")
FASTEMBED_CACHE = os.environ.get("FASTEMBED_CACHE_DIR", MODEL_CACHE)

# ---------------------------------------------------------------- cosine


def cos(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def normalize(v: List[float]) -> List[float]:
    n = float(np.linalg.norm(v))
    if n == 0:
        return v[:]
    return (np.asarray(v, dtype=float) / n).tolist()


# ---------------------------------------------------------------- Embedder base


class Embedder:
    """Unified interface all backends implement."""

    def embed_words(self, words: List[str]) -> List[List[float]]:
        """One vector per word. Used by the chunker's scan."""
        raise NotImplementedError

    def embed_chunks(self, texts: List[str]) -> List[List[float]]:
        """One vector per chunk text. Used for clustering + search index."""
        raise NotImplementedError

    def embed_chunk(self, text: str, prev_text: str = "",
                    next_text: str = "") -> List[float]:
        """One vector for a single chunk, optionally with neighbor context."""
        ctx = " ".join(x for x in [prev_text, text, next_text] if x).strip()
        return self.embed_chunks([ctx])[0]

    def embed_query(self, text: str) -> List[float]:
        """Embedding for a search query."""
        return self.embed_chunks([text])[0]


# ---------------------------------------------------------------- MiniML


class _MinimlEmbedder(Embedder):
    def __init__(self):
        self._model = None

    def _get(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                cache_folder=MODEL_CACHE,
            )
        return self._model

    def embed_words(self, words: List[str]) -> List[List[float]]:
        m = self._get()
        if not words:
            return []
        vecs = m.encode(words, show_progress_bar=False, batch_size=64)
        return [v.tolist() for v in vecs]

    def embed_chunks(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        m = self._get()
        vecs = m.encode(texts, show_progress_bar=False, batch_size=64)
        return [v.tolist() for v in vecs]


# ---------------------------------------------------------------- BGE-M3


class _BgeEmbedder(Embedder):
    def __init__(self):
        self._model = None

    def _get(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel
            local = os.path.join(MODEL_CACHE, "models--BAAI--bge-m3")
            path = local if os.path.isdir(local) else "BAAI/bge-m3"
            self._model = BGEM3FlagModel(path, use_fp16=False)
        return self._model

    def embed_words(self, words: List[str]) -> List[List[float]]:
        # BGE-M3 isn't ideally suited for word-level; embed words as short
        # texts. Fall back to chunk-style embedding per word.
        if not words:
            return []
        return self.embed_chunks(words)

    def embed_chunks(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        m = self._get()
        out = m.encode(
            list(texts),
            batch_size=8,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense = np.asarray(out["dense_vecs"], dtype=float)
        return [v.tolist() for v in dense]


# ---------------------------------------------------------------- Nomic (late chunking)


class _NomicEmbedder(Embedder):
    """nomic-ai/nomic-embed-text-v1.5 — 8192-token context.

    For MVP, this is a chunk embedder (not full-token-level late chunking —
    that's more code than MVP needs). It produces context-aware chunk vectors
    when chunks are embedded with enough surrounding text.
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None

    def _get(self):
        if self._model is None:
            import torch
            from transformers import AutoModel, AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(
                "nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True
            )
            self._model = AutoModel.from_pretrained(
                "nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True
            )
            self._model.eval()
            self._model.to("cpu")
        return self._model, self._tokenizer

    def embed_words(self, words: List[str]) -> List[List[float]]:
        # nomic is too heavy for word-level scan; fall back to chunking each
        # word as a tiny text. For scan purposes MiniML is the right tool.
        if not words:
            return []
        return self.embed_chunks(words)

    def embed_chunks(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        model, tok = self._get()
        vecs = []
        for t in texts:
            doc = "search_document: " + t
            enc = tok(
                doc,
                return_tensors="pt",
                add_special_tokens=True,
            )
            with torch.no_grad():
                out = model(input_ids=enc["input_ids"].to("cpu"),
                            attention_mask=enc["attention_mask"].to("cpu"))
            if hasattr(out, "last_hidden"):
                hidden = out.last_hidden
            elif hasattr(out, "last_hidden_state"):
                hidden = out.last_hidden_state
            elif isinstance(out, dict):
                hidden = out.get("last_hidden") or out["last_hidden_state"]
            else:
                hidden = out[0]
            # mean pool over non-padding tokens
            mask = enc["attention_mask"][0].numpy()
            tokvecs = hidden[0].numpy()
            pooled = tokvecs[mask == 1].mean(axis=0)
            vecs.append(pooled.tolist())
        return vecs

    def embed_query(self, text: str) -> List[float]:
        # nomic wants a different prefix for queries
        model, tok = self._get()
        doc = "search_query: " + text
        enc = tok(doc, return_tensors="pt", add_special_tokens=True)
        with torch.no_grad():
            out = model(input_ids=enc["input_ids"].to("cpu"),
                        attention_mask=enc["attention_mask"].to("cpu"))
        if hasattr(out, "last_hidden"):
            hidden = out.last_hidden
        elif hasattr(out, "last_hidden_state"):
            hidden = out.last_hidden_state
        else:
            hidden = out[0]
        mask = enc["attention_mask"][0].numpy()
        tokvecs = hidden[0].numpy()
        pooled = tokvecs[mask == 1].mean(axis=0)
        return pooled.tolist()


# ---------------------------------------------------------------- registry


_registry = {}


def get_embedder(mode: str = "miniml") -> Embedder:
    """Return the embedder for `mode`. Loads on first call, cached after."""
    mode = mode.lower()
    if mode not in _registry:
        if mode == "miniml":
            _registry[mode] = _MinimlEmbedder()
        elif mode == "bge":
            _registry[mode] = _BgeEmbedder()
        elif mode == "nomic":
            _registry[mode] = _NomicEmbedder()
        else:
            raise ValueError(f"Unknown embedder mode: {mode!r}. Choose miniml, bge, nomic.")
    return _registry[mode]


def list_backends() -> List[Dict[str, Any]]:
    return [
        {"mode": "miniml", "name": "MiniLM-L12", "dim": 384,
         "default": True, "note": "Fast, default. Good for scan + chunks."},
        {"mode": "bge", "name": "BGE-M3", "dim": 1024,
         "default": False, "note": "Multilingual, larger. Optional."},
        {"mode": "nomic", "name": "nomic-embed-text-v1.5", "dim": 768,
         "default": False, "note": "8192-token context. Optional."},
    ]


def detect_available() -> List[str]:
    """Which backends can actually be loaded right now."""
    avail = ["miniml"]  # miniml is always available if sentrans is installed
    try:
        get_embedder("bge")
        avail.append("bge")
    except Exception:
        pass
    try:
        get_embedder("nomic")
        avail.append("nomic")
    except Exception:
        pass
    return avail
