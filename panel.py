"""v11 Panel state — persisted panel layout for the cockpit.

Panels are stackable, groupable (tabs), closable, reorderable.
Layout persisted to data/panels.json.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional


DEFAULT_LAYOUT = [
    {"type": "dashboard", "group": "main", "title": "Dashboard", "config": {}},
    {"type": "stream", "group": "main", "title": "Stream", "config": {"rows": 50}},
    {"type": "search", "group": "main", "title": "Search", "config": {"engine": "semantic", "limit": 10}},
    {"type": "topography", "group": "machine", "title": "Topography", "config": {"skin": "city", "auto_rotate": True}},
    {"type": "cabinet", "group": "machine", "title": "Cabinet", "config": {}},
    {"type": "files", "group": "files", "title": "Files", "config": {}},
    {"type": "llm", "group": "main", "title": "LLM", "config": {}},
]

PANEL_TYPES = [p["type"] for p in DEFAULT_LAYOUT]


class PanelManager:
    """In-memory panel layout, persisted to data/panels.json."""

    def __init__(self, db_dir: str):
        self.db_dir = db_dir
        self.panels: Dict[str, Dict[str, Any]] = {}
        self.groups: Dict[str, List[str]] = {}  # group -> [panel_id, ...]
        self._load()

    def _path(self) -> str:
        return os.path.join(self.db_dir, "panels.json")

    def _load(self):
        p = Path(self._path())
        if not p.is_file():
            self._init_defaults()
            self._save()
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            self._init_defaults()
            self._save()
            return
        for pid, panel in data.get("panels", {}).items():
            self.panels[pid] = panel
            g = panel.get("group", "main")
            self.groups.setdefault(g, []).append(pid)
        for g, order in data.get("groups", {}).items():
            if g in self.groups:
                self.groups[g] = order

    def _init_defaults(self):
        for i, spec in enumerate(DEFAULT_LAYOUT):
            pid = f"panel_{i}_{spec['type']}"
            self.panels[pid] = {
                "id": pid,
                "type": spec["type"],
                "group": spec["group"],
                "title": spec["title"],
                "config": dict(spec.get("config", {})),
                "opened": True,
            }
            self.groups.setdefault(spec["group"], []).append(pid)

    def _save(self):
        Path(self._path()).parent.mkdir(parents=True, exist_ok=True)
        data = {"panels": self.panels, "groups": self.groups}
        Path(self._path()).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                      encoding="utf-8")

    def get_panels(self, group: str = None) -> List[Dict[str, Any]]:
        if group:
            ids = self.groups.get(group, [])
            return [self.panels[pid] for pid in ids if pid in self.panels]
        out = []
        for g in ["main", "machine", "files"]:
            if g in self.groups:
                for pid in self.groups[g]:
                    if pid in self.panels:
                        out.append(self.panels[pid])
        return out

    def get_all(self) -> Dict[str, Any]:
        return {
            "panels": self.panels,
            "groups": self.groups,
        }

    def open_panel(self, panel_id: str):
        if panel_id in self.panels:
            self.panels[panel_id]["opened"] = True
            self._save()

    def close_panel(self, panel_id: str):
        if panel_id in self.panels:
            self.panels[panel_id]["opened"] = False
            self._save()

    def set_config(self, panel_id: str, config: Dict[str, Any]):
        if panel_id in self.panels:
            self.panels[panel_id]["config"] = {**self.panels[panel_id].get("config", {}), **config}
            self._save()

    def set_title(self, panel_id: str, title: str):
        if panel_id in self.panels:
            self.panels[panel_id]["title"] = title
            self._save()

    def add_panel(self, type_: str, group: str = "main", title: str = None) -> Dict[str, Any]:
        if type_ not in PANEL_TYPES:
            raise ValueError(f"Unknown panel type: {type_}")
        pid = f"panel_{len(self.panels)}_{type_}"
        panel = {
            "id": pid,
            "type": type_,
            "group": group,
            "title": title or type_.title(),
            "config": {},
            "opened": True,
        }
        self.panels[pid] = panel
        self.groups.setdefault(group, []).append(pid)
        self._save()
        return panel

    def remove_panel(self, panel_id: str):
        if panel_id in self.panels:
            g = self.panels[panel_id].get("group", "main")
            self.groups.get(g, []).remove(panel_id)
            del self.panels[panel_id]
            self._save()

    def move_panel(self, panel_id: str, to_group: str, before_id: str = None):
        if panel_id not in self.panels:
            return
        old_group = self.panels[panel_id].get("group", "main")
        self.groups.get(old_group, []).remove(panel_id)
        self.panels[panel_id]["group"] = to_group
        target = self.groups.setdefault(to_group, [])
        if before_id and before_id in target:
            target.insert(target.index(before_id), panel_id)
        else:
            target.append(panel_id)
        self._save()
