"""Pure stdlib + Pillow SVG rasterizer for the bundled Lucide-style icon
library (widgets/icons.py's ICONS_DIR). This machine has no internet/pip
access, so svglib/cairosvg aren't an option — this covers exactly the
subset those icons use (flat <svg> with path/circle/rect/line/polyline/
polygon/ellipse, stroke-only, viewBox "0 0 24 24", path commands
M/L/H/V/C/S/Q/T/A/Z including elliptical arcs) rather than being a
general-purpose SVG engine."""

import math
import re
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

SUPERSAMPLE = 4
CURVE_SEGMENTS = 16
ARC_SEGMENTS = 24
ELLIPSE_SEGMENTS = 32

_POINTS_RE = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def _parse_viewbox(root):
    vb = root.get("viewBox")
    if vb:
        parts = [float(p) for p in vb.replace(",", " ").split()]
        if len(parts) == 4:
            return parts
    w = float(root.get("width", 24) or 24)
    h = float(root.get("height", 24) or 24)
    return [0.0, 0.0, w, h]


def _read_number(s, i):
    n = len(s)
    start = i
    if i < n and s[i] in "+-":
        i += 1
    while i < n and s[i].isdigit():
        i += 1
    if i < n and s[i] == ".":
        i += 1
        while i < n and s[i].isdigit():
            i += 1
    if i < n and s[i] in "eE":
        j = i + 1
        if j < n and s[j] in "+-":
            j += 1
        if j < n and s[j].isdigit():
            i = j
            while i < n and s[i].isdigit():
                i += 1
    return float(s[start:i]), i


def _read_flag(s, i):
    return float(s[i]), i + 1


def _skip_sep(s, i):
    n = len(s)
    while i < n and (s[i].isspace() or s[i] == ","):
        i += 1
    return i


def _cubic_bezier(p0, p1, p2, p3, segments=CURVE_SEGMENTS):
    pts = []
    for i in range(1, segments + 1):
        t = i / segments
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def _quad_bezier(p0, p1, p2, segments=CURVE_SEGMENTS):
    pts = []
    for i in range(1, segments + 1):
        t = i / segments
        mt = 1 - t
        x = mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0]
        y = mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1]
        pts.append((x, y))
    return pts


def _angle(ux, uy, vx, vy):
    length = math.sqrt((ux * ux + uy * uy) * (vx * vx + vy * vy))
    if not length:
        return 0.0
    dot = max(-1.0, min(1.0, (ux * vx + uy * vy) / length))
    a = math.acos(dot)
    return -a if ux * vy - uy * vx < 0 else a


def _arc(p0, rx, ry, rot_deg, large_arc, sweep, p1, segments=ARC_SEGMENTS):
    """Endpoint-to-center parameterization per the SVG 1.1 spec (F.6.5)."""
    x1, y1 = p0
    x2, y2 = p1
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [p1]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rot_deg % 360)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)

    dx2, dy2 = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    rx_sq, ry_sq = rx * rx, ry * ry
    x1p_sq, y1p_sq = x1p * x1p, y1p * y1p
    lam = x1p_sq / rx_sq + y1p_sq / ry_sq
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s
        ry *= s
        rx_sq, ry_sq = rx * rx, ry * ry

    den = rx_sq * y1p_sq + ry_sq * x1p_sq
    num = rx_sq * ry_sq - rx_sq * y1p_sq - ry_sq * x1p_sq
    coef = math.sqrt(max(num / den, 0)) if den else 0.0
    if large_arc == sweep:
        coef = -coef
    cxp = coef * (rx * y1p) / ry
    cyp = coef * -(ry * x1p) / rx

    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2

    theta1 = _angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = _angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)

    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    pts = []
    for i in range(1, segments + 1):
        t = theta1 + delta * i / segments
        x = cx + rx * cos_phi * math.cos(t) - ry * sin_phi * math.sin(t)
        y = cy + rx * sin_phi * math.cos(t) + ry * cos_phi * math.sin(t)
        pts.append((x, y))
    return pts


def parse_path(d):
    """Flattens an SVG path 'd' string into a list of subpaths, each a
    flat list of (x, y) points with curves/arcs already sampled."""
    i = 0
    n = len(d)
    cmd = None
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    subpaths = []
    pts = []
    prev_ctrl = None
    prev_cmd = None

    def flush():
        nonlocal pts
        if len(pts) >= 2:
            subpaths.append(pts)
        pts = []

    while i < n:
        i = _skip_sep(d, i)
        if i >= n:
            break
        ch = d[i]
        if ch.isalpha():
            cmd = ch
            i += 1
            i = _skip_sep(d, i)
        if cmd is None:
            break

        upper = cmd.upper()
        rel = cmd.islower()

        if upper == "Z":
            if pts:
                pts.append(start)
            flush()
            cur = start
            prev_cmd = "Z"
            continue

        if upper == "M":
            x, i = _read_number(d, i)
            i = _skip_sep(d, i)
            y, i = _read_number(d, i)
            i = _skip_sep(d, i)
            if rel:
                x += cur[0]
                y += cur[1]
            flush()
            cur = (x, y)
            start = cur
            pts = [cur]
            cmd = "l" if rel else "L"
            prev_cmd = "M"
            continue

        if upper == "L":
            x, i = _read_number(d, i)
            i = _skip_sep(d, i)
            y, i = _read_number(d, i)
            i = _skip_sep(d, i)
            if rel:
                x += cur[0]
                y += cur[1]
            cur = (x, y)
            pts.append(cur)
            prev_cmd = "L"
            continue

        if upper == "H":
            x, i = _read_number(d, i)
            i = _skip_sep(d, i)
            if rel:
                x += cur[0]
            cur = (x, cur[1])
            pts.append(cur)
            prev_cmd = "H"
            continue

        if upper == "V":
            y, i = _read_number(d, i)
            i = _skip_sep(d, i)
            if rel:
                y += cur[1]
            cur = (cur[0], y)
            pts.append(cur)
            prev_cmd = "V"
            continue

        if upper == "C":
            x1, i = _read_number(d, i); i = _skip_sep(d, i)
            y1, i = _read_number(d, i); i = _skip_sep(d, i)
            x2, i = _read_number(d, i); i = _skip_sep(d, i)
            y2, i = _read_number(d, i); i = _skip_sep(d, i)
            x, i = _read_number(d, i); i = _skip_sep(d, i)
            y, i = _read_number(d, i); i = _skip_sep(d, i)
            if rel:
                x1 += cur[0]; y1 += cur[1]
                x2 += cur[0]; y2 += cur[1]
                x += cur[0]; y += cur[1]
            pts.extend(_cubic_bezier(cur, (x1, y1), (x2, y2), (x, y)))
            prev_ctrl = (x2, y2)
            cur = (x, y)
            prev_cmd = "C"
            continue

        if upper == "S":
            x2, i = _read_number(d, i); i = _skip_sep(d, i)
            y2, i = _read_number(d, i); i = _skip_sep(d, i)
            x, i = _read_number(d, i); i = _skip_sep(d, i)
            y, i = _read_number(d, i); i = _skip_sep(d, i)
            if rel:
                x2 += cur[0]; y2 += cur[1]
                x += cur[0]; y += cur[1]
            if prev_cmd in ("C", "S") and prev_ctrl is not None:
                x1 = 2 * cur[0] - prev_ctrl[0]
                y1 = 2 * cur[1] - prev_ctrl[1]
            else:
                x1, y1 = cur
            pts.extend(_cubic_bezier(cur, (x1, y1), (x2, y2), (x, y)))
            prev_ctrl = (x2, y2)
            cur = (x, y)
            prev_cmd = "S"
            continue

        if upper == "Q":
            x1, i = _read_number(d, i); i = _skip_sep(d, i)
            y1, i = _read_number(d, i); i = _skip_sep(d, i)
            x, i = _read_number(d, i); i = _skip_sep(d, i)
            y, i = _read_number(d, i); i = _skip_sep(d, i)
            if rel:
                x1 += cur[0]; y1 += cur[1]
                x += cur[0]; y += cur[1]
            pts.extend(_quad_bezier(cur, (x1, y1), (x, y)))
            prev_ctrl = (x1, y1)
            cur = (x, y)
            prev_cmd = "Q"
            continue

        if upper == "T":
            x, i = _read_number(d, i); i = _skip_sep(d, i)
            y, i = _read_number(d, i); i = _skip_sep(d, i)
            if rel:
                x += cur[0]
                y += cur[1]
            if prev_cmd in ("Q", "T") and prev_ctrl is not None:
                x1 = 2 * cur[0] - prev_ctrl[0]
                y1 = 2 * cur[1] - prev_ctrl[1]
            else:
                x1, y1 = cur
            pts.extend(_quad_bezier(cur, (x1, y1), (x, y)))
            prev_ctrl = (x1, y1)
            cur = (x, y)
            prev_cmd = "T"
            continue

        if upper == "A":
            rx, i = _read_number(d, i); i = _skip_sep(d, i)
            ry, i = _read_number(d, i); i = _skip_sep(d, i)
            rot, i = _read_number(d, i); i = _skip_sep(d, i)
            large_arc, i = _read_flag(d, i); i = _skip_sep(d, i)
            sweep, i = _read_flag(d, i); i = _skip_sep(d, i)
            x, i = _read_number(d, i); i = _skip_sep(d, i)
            y, i = _read_number(d, i); i = _skip_sep(d, i)
            if rel:
                x += cur[0]
                y += cur[1]
            pts.extend(_arc(cur, rx, ry, rot, large_arc, sweep, (x, y)))
            cur = (x, y)
            prev_cmd = "A"
            continue

        break  # unrecognized command — stop rather than loop forever

    flush()
    return subpaths


def _parse_points(s):
    nums = [float(n) for n in _POINTS_RE.findall(s or "")]
    return list(zip(nums[0::2], nums[1::2]))


def _ellipse_ring(cx, cy, rx, ry, segments=ELLIPSE_SEGMENTS):
    return [
        (cx + rx * math.cos(2 * math.pi * i / segments), cy + ry * math.sin(2 * math.pi * i / segments))
        for i in range(segments + 1)
    ]


def _stroke_polyline(draw, points, color, width):
    if len(points) < 2:
        return
    try:
        draw.line(points, fill=color, width=width, joint="curve")
    except TypeError:
        draw.line(points, fill=color, width=width)
    r = width / 2
    for x, y in points:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def render_svg(path, size=40, color="#8A96A3"):
    """Rasterizes a Lucide-style SVG to a PIL RGBA image, or None if the
    file can't be parsed. Renders supersampled then downsamples for
    anti-aliasing, since PIL's own line/ellipse drawing has none."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None

    vb_x, vb_y, vb_w, vb_h = _parse_viewbox(root)
    if vb_w <= 0 or vb_h <= 0:
        return None

    canvas = size * SUPERSAMPLE
    scale = canvas / max(vb_w, vb_h)
    try:
        stroke_width = max(1, round(float(root.get("stroke-width", 2)) * scale))
    except ValueError:
        stroke_width = max(1, round(2 * scale))

    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def tx(x, y):
        return ((x - vb_x) * scale, (y - vb_y) * scale)

    try:
        for el in root.iter():
            tag = _strip_ns(el.tag)
            a = el.attrib
            if tag == "circle":
                cx, cy, r = float(a.get("cx", 0)), float(a.get("cy", 0)), float(a.get("r", 0))
                box = tx(cx - r, cy - r) + tx(cx + r, cy + r)
                draw.ellipse(list(box), outline=color, width=stroke_width)
            elif tag == "ellipse":
                cx, cy = float(a.get("cx", 0)), float(a.get("cy", 0))
                rx, ry = float(a.get("rx", 0)), float(a.get("ry", 0))
                box = tx(cx - rx, cy - ry) + tx(cx + rx, cy + ry)
                draw.ellipse(list(box), outline=color, width=stroke_width)
            elif tag == "rect":
                x, y = float(a.get("x", 0)), float(a.get("y", 0))
                w, h = float(a.get("width", 0)), float(a.get("height", 0))
                rx_attr, ry_attr = a.get("rx"), a.get("ry")
                radius = float(rx_attr) if rx_attr is not None else (float(ry_attr) if ry_attr is not None else 0)
                box = list(tx(x, y)) + list(tx(x + w, y + h))
                if radius > 0:
                    draw.rounded_rectangle(box, radius=radius * scale, outline=color, width=stroke_width)
                else:
                    draw.rectangle(box, outline=color, width=stroke_width)
            elif tag == "line":
                p0 = tx(float(a.get("x1", 0)), float(a.get("y1", 0)))
                p1 = tx(float(a.get("x2", 0)), float(a.get("y2", 0)))
                _stroke_polyline(draw, [p0, p1], color, stroke_width)
            elif tag == "polyline":
                pts = [tx(x, y) for x, y in _parse_points(a.get("points", ""))]
                _stroke_polyline(draw, pts, color, stroke_width)
            elif tag == "polygon":
                pts = [tx(x, y) for x, y in _parse_points(a.get("points", ""))]
                if pts:
                    pts.append(pts[0])
                _stroke_polyline(draw, pts, color, stroke_width)
            elif tag == "path":
                for sub in parse_path(a.get("d", "")):
                    _stroke_polyline(draw, [tx(x, y) for x, y in sub], color, stroke_width)
    except (ValueError, ZeroDivisionError) as e:
        print(f"[svg_render] failed to render {path!r}: {e}")
        return None

    return img.resize((size, size), Image.LANCZOS)
