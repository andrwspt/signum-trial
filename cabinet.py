"""v11 Cabinet — file-cabinet view data prep.

Turns cluster geometry into a "file cabinet" data structure the client
renders as drawers (clusters) containing papers (chunks).
"""
from __future__ import annotations
from typing import List, Dict, Any


def build_cabinet(clusters: List[Dict[str, Any]],
                  points: List[Dict[str, Any]],
                  notes: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build cabinet view data.

    Returns:
        {
            "drawers": [
                {
                    "id": int,
                    "name": str,
                    "color": str,
                    "member_count": int,
                    "papers": [
                        {
                            "id": str,
                            "text": str,
                            "note_id": str,
                            "note_path": str,
                            "start": int,
                            "end": int,
                        },
                        ...
                    ],
                },
                ...
            ],
            "total_papers": int,
        }
    """
    path_by_note: Dict[str, str] = {}
    if notes:
        for n in notes:
            path_by_note[n.get("id", "")] = n.get("path", "")

    palette = [
        "#c2410c", "#1570ef", "#12a150", "#b42318",
        "#7839ee", "#b54708", "#0e7490", "#7c2d12",
        "#f59e0b", "#8b5cf6", "#06b6d4", "#ec4899",
    ]

    drawers = []
    for c in clusters:
        members = [p for p in points if p.get("cluster") == c["id"]]
        members.sort(key=lambda p: p.get("start", 0))
        papers = []
        for p in members:
            papers.append({
                "id": p.get("id", ""),
                "text": p.get("text", "")[:280],
                "note_id": p.get("note_id", ""),
                "note_path": path_by_note.get(p.get("note_id", ""), ""),
                "start": p.get("start", 0),
                "end": p.get("end", 0),
            })
        drawers.append({
            "id": c["id"],
            "name": c.get("name", f"Cluster {c['id']}"),
            "color": palette[c["id"] % len(palette)],
            "member_count": c.get("member_count", len(members)),
            "papers": papers,
        })

    return {
        "drawers": drawers,
        "total_papers": sum(len(d["papers"]) for d in drawers),
    }
