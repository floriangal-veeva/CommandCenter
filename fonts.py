"""Enumerates installed system fonts via tkinter.font.families() and filters
a monospace-capable subset for the mono font dropdown."""

import tkinter
import tkinter.font as tkfont

# Fonts that render proportionally despite sometimes-ambiguous family names,
# or that tkinter reports but don't actually make good monospace candidates.
_KNOWN_MONO_SUBSTRINGS = (
    "consolas", "courier", "cascadia", "lucida console", "terminal",
    "dejavu sans mono", "source code", "fira code", "fira mono",
    "jetbrains", "menlo", "monaco", "roboto mono", "ubuntu mono",
    "ibm plex mono", "iosevka", "hack", "inconsolata", "sf mono",
    "mono",
)


def _ensure_root():
    if tkinter._default_root is None:
        root = tkinter.Tk()
        root.withdraw()
        return root
    return tkinter._default_root


def list_all_fonts():
    _ensure_root()
    families = sorted(set(tkfont.families()), key=str.lower)
    return [f for f in families if f and not f.startswith("@")]


def list_monospace_fonts():
    all_fonts = list_all_fonts()
    mono = [f for f in all_fonts if any(sub in f.lower() for sub in _KNOWN_MONO_SUBSTRINGS)]
    return mono if mono else all_fonts
