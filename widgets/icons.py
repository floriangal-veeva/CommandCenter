"""Icon sourcing for the Launcher's tiled grid: real icons extracted from
.exe/.lnk/.ico files via pywin32, or a procedurally-drawn placeholder glyph
for URLs and anything an icon can't be extracted from. No bundled image
assets, no network fetch — everything is generated or pulled from the file
system at runtime."""

import io
import json
import os
import shutil
import urllib.request
from urllib.parse import urlparse

import customtkinter as ctk
from PIL import Image, ImageDraw

_ICON_CACHE = {}
_GLYPH_COLOR = "#8A96A3"

# Bundled local icon library (user-downloaded, e.g. Lucide) — fully
# offline, no cloud API. command_center/icons/*.svg (+ matching .json for
# search tags). Nothing is bundled by us; this is just where we look.
ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")
_ICON_INDEX = None


def _extract_file_icon(path, size):
    import win32gui
    import win32ui

    large, small = win32gui.ExtractIconEx(path, 0)
    handles = (large or []) + (small or [])
    if not handles:
        return None
    hicon = handles[0]

    hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
    hbmp = win32ui.CreateBitmap()
    hbmp.CreateCompatibleBitmap(hdc, size, size)
    hdc_mem = hdc.CreateCompatibleDC()
    hdc_mem.SelectObject(hbmp)
    hdc_mem.DrawIcon((0, 0), hicon)

    bmpinfo = hbmp.GetInfo()
    bmpstr = hbmp.GetBitmapBits(True)
    img = Image.frombuffer(
        "RGBA", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRA", 0, 1
    )

    for h in handles:
        win32gui.DestroyIcon(h)
    hdc_mem.DeleteDC()
    hdc.DeleteDC()

    return img.resize((size, size), Image.LANCZOS)


def _draw_link_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size * 0.14
    width = max(2, size // 14)
    draw.ellipse([pad, pad, size - pad, size - pad], outline=_GLYPH_COLOR, width=width)
    draw.line([size * 0.18, size * 0.5, size * 0.82, size * 0.5], fill=_GLYPH_COLOR, width=width)
    draw.ellipse([size * 0.38, pad, size * 0.62, size - pad], outline=_GLYPH_COLOR, width=max(1, width - 1))
    return img


def _draw_app_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size * 0.16
    width = max(2, size // 14)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad], radius=size * 0.14, outline=_GLYPH_COLOR, width=width
    )
    return img


def get_icon_image(target, size=40):
    key = (target, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    is_url = target.lower().startswith(("http://", "https://"))
    pil_image = None

    if is_url:
        pil_image = _draw_link_icon(size)
    else:
        resolved = target if os.path.exists(target) else (shutil.which(target) or "")
        if resolved and os.path.exists(resolved):
            try:
                pil_image = _extract_file_icon(resolved, size)
            except Exception as e:
                print(f"[icons] failed to extract icon for {target!r}: {e}")

    if pil_image is None:
        pil_image = _draw_app_icon(size)

    ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(size, size))
    _ICON_CACHE[key] = ctk_image
    return ctk_image


def load_custom_icon_image(path, size=40):
    """User-selected icon file: any Pillow-readable format (.ico/.png/.jpg/...),
    or an .svg (rasterized via svglib+reportlab if installed). Returns None
    if the file can't be read/rendered, so callers can fall back."""
    key = ("custom", path, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    if path.lower().endswith(".svg"):
        pil_image = render_svg_icon(path, size=size)
    else:
        try:
            pil_image = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception as e:
            print(f"[icons] failed to load custom icon {path!r}: {e}")
            pil_image = None

    if pil_image is None:
        return None
    ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(size, size))
    _ICON_CACHE[key] = ctk_image
    return ctk_image


def render_svg_icon(path, size=40, color=_GLYPH_COLOR):
    """Rasterize an SVG (e.g. a Lucide icon — stroke="currentColor", no
    fill) to a PIL image, via our own pure stdlib+Pillow renderer
    (widgets/svg_render.py) — no pip install needed/available on this
    offline fleet laptop. Returns None on failure so the caller falls
    back to the placeholder glyph instead of crashing."""
    from widgets.svg_render import render_svg

    try:
        return render_svg(path, size=size, color=color)
    except Exception as e:
        print(f"[icons] failed to render SVG {path!r}: {e}")
        return None


def list_bundled_icons():
    """Index of (name, path, tags) for every .svg in ICONS_DIR, built once.
    Tags come from the matching Lucide-style .json sidecar if present."""
    global _ICON_INDEX
    if _ICON_INDEX is not None:
        return _ICON_INDEX

    index = []
    if os.path.isdir(ICONS_DIR):
        for fname in sorted(os.listdir(ICONS_DIR)):
            if not fname.lower().endswith(".svg"):
                continue
            name = os.path.splitext(fname)[0]
            tags = []
            json_path = os.path.join(ICONS_DIR, name + ".json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    tags = list(data.get("tags", [])) + list(data.get("categories", []))
                except Exception:
                    pass
            index.append({"name": name, "path": os.path.join(ICONS_DIR, fname), "tags": tags})
    _ICON_INDEX = index
    return index


def search_bundled_icons(query, limit=48):
    query = (query or "").strip().lower()
    items = list_bundled_icons()
    if not query:
        return items[:limit]
    matches = []
    for item in items:
        if query in item["name"].lower() or any(query in tag.lower() for tag in item["tags"]):
            matches.append(item)
            if len(matches) >= limit:
                break
    return matches


def fetch_favicon_image(url, size=40, timeout=5.0):
    """Blocking network fetch — call from a background thread only, never
    from the UI thread. Tries the linked site's own favicon.ico directly
    (no third-party icon API/aggregator) and fails silently to None, same
    offline-safe pattern as the rest of the app's network calls."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return None
        favicon_url = f"{parsed.scheme or 'https'}://{domain}/favicon.ico"
        req = urllib.request.Request(favicon_url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=timeout).read()
        img = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception as e:
        print(f"[icons] favicon fetch failed for {url!r}: {e}")
        return None
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
