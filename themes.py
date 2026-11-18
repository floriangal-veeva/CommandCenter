"""Loads themes.json and applies theme dicts to widgets. No colors hardcoded here
beyond the last-resort fallback used if a theme is missing *every* role."""

import json
import os

ACCENT_ROLES = ["primary", "secondary", "tertiary", "success", "danger"]
TEXT_ROLES = ["text", "text_muted"]
SURFACE_ROLES = ["surface", "border"]
ALL_ROLES = ["background", "surface", "border", "text", "text_muted"] + ACCENT_ROLES

THEMES_PATH = os.path.join(os.path.dirname(__file__), "themes.json")


def contrasting_text_color(hex_color):
    """Pick black or white text for readable contrast against hex_color
    (relative-luminance heuristic), instead of assuming a role like
    "background" is always dark — custom themes (via + Add Theme) can make
    any role bright, and accent colors (primary/tertiary) vary in
    brightness theme to theme."""
    hex_color = (hex_color or "").lstrip("#")
    if len(hex_color) != 6:
        return "#FFFFFF"
    try:
        r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#FFFFFF"
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.6 else "#FFFFFF"


def _normalize(theme):
    """Fill missing roles per the fallback rules in spec §6."""
    t = dict(theme)

    if not t.get("background"):
        t["background"] = "#000000"
    if not t.get("text"):
        t["text"] = "#FFFFFF"

    for role in SURFACE_ROLES:
        if not t.get(role):
            t[role] = t["background"]

    for role in TEXT_ROLES:
        if not t.get(role):
            t[role] = t["text"]

    for role in ACCENT_ROLES:
        if not t.get(role):
            t[role] = t.get("primary") or t["text"]

    return t


class ThemeManager:
    def __init__(self, path=THEMES_PATH):
        self.path = path
        self._raw = {}
        self._listeners = []
        self.reload()

    def reload(self):
        with open(self.path, "r", encoding="utf-8") as f:
            self._raw = json.load(f)

    def theme_names(self):
        return list(self._raw.keys())

    def get_theme(self, name):
        if name not in self._raw:
            name = next(iter(self._raw))
        return _normalize(self._raw[name])

    def register(self, widget):
        """Widget must implement .apply_theme(theme_dict)."""
        self._listeners.append(widget)

    def unregister(self, widget):
        """For widgets that come and go (e.g. the Notes window) — stops
        re-theming something that's been destroyed."""
        if widget in self._listeners:
            self._listeners.remove(widget)

    def save_theme(self, name, role_dict):
        """Adds/overwrites a theme and persists themes.json atomically —
        new themes just need to land here, no code change required for the
        dropdown to pick them up."""
        self._raw[name] = {role: role_dict.get(role, "") for role in ALL_ROLES}
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._raw, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.path)

    def apply(self, name):
        theme = self.get_theme(name)
        for widget in list(self._listeners):
            try:
                widget.apply_theme(theme)
            except Exception as e:
                print(f"[themes] apply_theme failed on {widget}: {e}")
        return theme
