"""v11 Clustering — threshold merge + PCA/k-means."""
from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any
import numpy as np


def cluster_threshold(vectors: List[List[float]], threshold: float = 0.75) -> List[int]:
    """Union-find: cosine similarity > threshold -> same cluster."""
    n = len(vectors)
    if n == 0:
        return []
    if n == 1:
        return [0]
    if n <= 2:
        return list(range(n))

    v = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vn = v / norms
    sim = vn @ vn.T

    clusters = list(range(n))
    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] > threshold:
                old, new = clusters[j], clusters[i]
                for k in range(n):
                    if clusters[k] == old:
                        clusters[k] = new
    # normalize cluster ids to 0..K-1
    mp: dict = {}
    nxt = 0
    for i in range(n):
        c = clusters[i]
        if c not in mp:
            mp[c] = nxt
            nxt += 1
        clusters[i] = mp[c]
    return clusters


def pca(vs: List[List[float]], k: int = 3) -> Tuple[List[List[float]], List[List[float]]]:
    """PCA on vectors -> 2D and 3D coords for the topography.
    Returns (coords_2d, coords_3d).
    """
    X = np.asarray(vs, dtype=float)
    n = X.shape[0]
    if n == 0:
        return [], []
    if n == 1:
        return [[0.0, 0.0]], [[0.0, 0.0, 0.0]]

    X = X - X.mean(axis=0)
    
    # Use SVD for PCA: X = U * S * Vt
    # The principal component coordinates are U * S
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    proj = U * S  # shape (n, min(n, d))
    
    # Take first k components, pad with zeros if needed
    if proj.shape[1] < k:
        pad = np.zeros((n, k - proj.shape[1]))
        proj = np.hstack([proj, pad])
    
    c2 = proj[:, :2].tolist()
    c3 = proj[:, :3].tolist()
    return c2, c3


def cluster_all(
    vectors: List[List[float]],
    threshold: float = 0.75,
    pca_k: int = 3,
) -> Dict[str, Any]:
    """Full clustering: threshold clusters + PCA coords + stats."""
    n = len(vectors)
    if n == 0:
        return {
            "cluster_ids": [], "n_clusters": 0,
            "pca_2d": [], "pca_3d": [], "centroids": [], "member_counts": [],
        }

    ids = cluster_threshold(vectors, threshold)
    n_clusters = max(ids) + 1 if ids else 0

    # PCA coords
    pca2, pca3 = pca(vectors, pca_k)

    # centroids + member counts
    v = np.asarray(vectors, dtype=float)
    centroids: List[List[float]] = []
    member_counts: List[int] = []
    for c in range(n_clusters):
        idxs = [i for i, ci in enumerate(ids) if ci == c]
        member_counts.append(len(idxs))
        if idxs:
            centroids.append(np.mean(v[idxs], axis=0).tolist())
        else:
            centroids.append([0.0] * (v.shape[1] if v.ndim == 2 else 384))

    return {
        "cluster_ids": ids,
        "n_clusters": n_clusters,
        "pca_2d": pca2,
        "pca_3d": pca3,
        "centroids": centroids,
        "member_counts": member_counts,
    }


def auto_name_clusters(texts: List[str], cluster_ids: List[int]) -> Dict[int, str]:
    """Auto-name clusters using TF-IDF top terms."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer(max_features=200, stop_words='english', min_df=1)
        tfidf = vectorizer.fit_transform(texts)
        terms = vectorizer.get_feature_names_out()
        
        names = {}
        unique_clusters = set(cluster_ids)
        for cid in unique_clusters:
            idxs = [i for i, c in enumerate(cluster_ids) if c == cid]
            if not idxs:
                names[cid] = f"Cluster {cid}"
                continue
            mean_scores = tfidf[idxs].mean(axis=0).A1
            top_idx = mean_scores.argsort()[-3:][::-1]
            top_terms = [terms[i] for i in top_idx if mean_scores[i] > 0]
            if top_terms:
                names[cid] = " · ".join(top_terms[:3])
            else:
                names[cid] = f"Cluster {cid}"
        return names
    except Exception:
        # Fallback if sklearn fails
        names = {}
        for cid in set(cluster_ids):
            names[cid] = f"Cluster {cid}"
        return names
