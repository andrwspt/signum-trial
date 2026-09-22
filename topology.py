"""v11 Topology — 3D topography data prep for the client.

Clients call /api/topology and get geometry they render. This module
prepares that geometry from chunk vectors: PCA coords, cluster assignment,
per-cluster centroids.
"""
from __future__ import annotations
import numpy as np
from typing import List, Dict, Any, Tuple


def pca_project(vectors: List[List[float]], dims: int = 3) -> List[List[float]]:
    """PCA project vectors to `dims` dimensions. Returns list of coords."""
    if not vectors:
        return []
    X = np.asarray(vectors, dtype=float)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    if X.shape[0] < 2:
        return [[0.0] * dims for _ in range(X.shape[0])]
    # center
    Xc = X - X.mean(axis=0)
    # covariance + eigendecomposition
    cov = np.cov(Xc.T)
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1][:dims]
    proj = Xc @ vecs[:, order]
    # pad if fewer dims than requested
    if proj.shape[1] < dims:
        pad = np.zeros((proj.shape[0], dims - proj.shape[1]))
        proj = np.hstack([proj, pad])
    return proj.tolist()


def assign_clusters(vectors: List[List[float]],
                    threshold: float = 0.75) -> Tuple[List[int], List[List[float]]]:
    """Greedy threshold clustering.

    Returns (cluster_ids, centroids): cluster_ids[i] = cluster for vector i.
    """
    n = len(vectors)
    if n == 0:
        return [], []
    V = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(V, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    Vn = V / norms

    clusters: List[int] = [-1] * n
    centroids: List[List[float]] = []
    for i in range(n):
        if clusters[i] != -1:
            continue
        # start new cluster
        cid = len(centroids)
        centroids.append(V[i].tolist())
        clusters[i] = cid
        for j in range(i + 1, n):
            if clusters[j] != -1:
                continue
            sim = float(np.dot(Vn[i], Vn[j]))
            if sim > threshold:
                clusters[j] = cid
        # re-centroid
        members = [k for k in range(n) if clusters[k] == cid]
        if members:
            centroids[cid] = np.mean(V[members], axis=0).tolist()
    return clusters, centroids


def topology_payload(chunks: List[Dict[str, Any]],
                     vectors: List[List[float]],
                     threshold: float = 0.75) -> Dict[str, Any]:
    """Build the /api/topology response from chunks + vectors.

    Returns:
        {
            "points": [
                {
                    "id": str,            # chunk id
                    "x3": float, "y3": float, "z3": float,   # PCA 3D
                    "x2": float, "y2": float,                 # PCA 2D (for 2D fallback)
                    "cluster": int,
                    "text": str,
                    "note_id": str,
                    "start": int,
                    "end": int,
                    "boundary_strength": float,
                },
                ...
            ],
            "clusters": [
                {
                    "id": int,
                    "name": str,
                    "centroid_3d": [float, float, float],
                    "centroid_2d": [float, float],
                    "member_count": int,
                    "member_ids": [str, ...],
                },
                ...
            ],
            "threshold": float,
        }
    """
    coords = pca_project(vectors, 3)
    coords2 = pca_project(vectors, 2)
    ids, centroids = assign_clusters(vectors, threshold)

    n_clusters = max(ids) + 1 if ids else 0
    cluster_members: Dict[int, List[int]] = {}
    for i, cid in enumerate(ids):
        cluster_members.setdefault(cid, []).append(i)

    points = []
    for i, c in enumerate(chunks):
        cid = ids[i] if i < len(ids) else -1
        p3 = coords[i] if i < len(coords) else [0.0, 0.0, 0.0]
        p2 = coords2[i] if i < len(coords2) else [0.0, 0.0]
        points.append({
            "id": c.get("id", ""),
            "x3": float(p3[0]), "y3": float(p3[1]), "z3": float(p3[2]),
            "x2": float(p2[0]), "y2": float(p2[1]),
            "cluster": cid,
            "text": c.get("text", "")[:300],
            "note_id": c.get("note_id", ""),
            "start": c.get("start", 0),
            "end": c.get("end", 0),
            "boundary_strength": c.get("boundary_strength", 0.0),
            "tags": c.get("tags", []),
            "metadata": c.get("metadata", {}),
            "vector": c.get("vector"),
        })

    clusters_out = []
    for cid in range(n_clusters):
        members = cluster_members.get(cid, [])
        member_ids = [chunks[m].get("id", "") for m in members]
        if not members:
            continue
        cx = sum(coords[m][0] for m in members) / len(members)
        cy = sum(coords[m][1] for m in members) / len(members)
        cz = sum(coords[m][2] for m in members) / len(members)
        clusters_out.append({
            "id": cid,
            "name": f"Cluster {cid}",
            "centroid_3d": [float(cx), float(cy), float(cz)],
            "centroid_2d": [float(cx), float(cy)],
            "member_count": len(members),
            "member_ids": member_ids,
        })

    return {
        "points": points,
        "clusters": clusters_out,
        "threshold": threshold,
    }
