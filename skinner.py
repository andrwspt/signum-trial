"""v11 Skinning — skin registry + engine contract.

A skin is a JS module that renders cluster state onto a 2D canvas context.
Built-in skins live in v11/skins/*.js. User skins live in v11/data/skins/*.js.

Skin file contract (JS):
  // @schema
  // {"$schema": "...", "type": "object", ...}
  Render = function(ctx, clusters, proj, t, panel_w, panel_h) {
      // draw on ctx using proj.project(x,y,z) -> {x, y, scale}
  };

Python side:
  list_skins()         -> list of {name, kind, path, schema, source}
  get_skin(name)       -> skin record with js text + schema
  save_user_skin(name, js_text) -> persists to data/skins/
  load_user_skin(name) -> skin record
"""
from __future__ import annotations
import os
import json
import re
from typing import List, Dict, Any, Optional

SKINS_DIR = os.path.join(os.path.dirname(__file__), "skins")
USER_SKINS_DIR = os.path.join(os.path.dirname(__file__), "data", "skins")

SCHEMA_COMMENT_RE = re.compile(r"//\s*@schema\s*\n(\{[^\n]+\})", re.DOTALL)


def _parse_schema(js_text: str) -> Optional[Dict[str, Any]]:
    m = SCHEMA_COMMENT_RE.search(js_text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _list_skin_files(directory: str) -> List[str]:
    if not os.path.isdir(directory):
        return []
    names = []
    for f in sorted(os.listdir(directory)):
        if f.endswith(".js"):
            names.append(f[:-3])
    return names


def _read_skin(name: str, directory: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(directory, f"{name}.js")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        js = f.read()
    return {
        "name": name,
        "kind": "built-in" if directory == SKINS_DIR else "user",
        "path": path,
        "source": js,
        "schema": _parse_schema(js),
    }


def list_skins() -> List[Dict[str, Any]]:
    """All skins: built-in + user, merged by name (user overrides built-in)."""
    skins: Dict[str, Dict[str, Any]] = {}
    for name in _list_skin_files(SKINS_DIR):
        skins[name] = _read_skin(name, SKINS_DIR)
    for name in _list_skin_files(USER_SKINS_DIR):
        skins[name] = _read_skin(name, USER_SKINS_DIR)
    return list(skins.values())


def get_skin(name: str) -> Optional[Dict[str, Any]]:
    """User skin takes precedence over built-in."""
    user = _read_skin(name, USER_SKINS_DIR)
    if user:
        return user
    return _read_skin(name, SKINS_DIR)


def save_user_skin(name: str, js_text: str):
    os.makedirs(USER_SKINS_DIR, exist_ok=True)
    path = os.path.join(USER_SKINS_DIR, f"{name}.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js_text)


def delete_user_skin(name: str):
    path = os.path.join(USER_SKINS_DIR, f"{name}.js")
    if os.path.isfile(path):
        os.remove(path)


def get_active_skin(name: str = "city") -> Dict[str, Any]:
    """The skin the UI should use. Falls back to 'city'."""
    skin = get_skin(name)
    if skin is None:
        skin = get_skin("city")
    if skin is None:
        raise RuntimeError("No built-in 'city' skin found")
    return skin
