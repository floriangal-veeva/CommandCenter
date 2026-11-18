"""One .txt file per note in ./notes/. Genuinely plain text — openable
directly in Notepad++ or any other editor outside the app. No metadata
sidecar: the filename (sans extension) IS the title."""

import os
import re

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify_filename(title):
    cleaned = _INVALID_CHARS.sub("", title).strip()
    return cleaned or "Untitled"


def list_note_files(notes_dir):
    os.makedirs(notes_dir, exist_ok=True)
    return sorted(
        (f for f in os.listdir(notes_dir) if f.lower().endswith(".txt")),
        key=str.lower,
    )


def next_default_name(notes_dir):
    existing_titles = {os.path.splitext(f)[0] for f in list_note_files(notes_dir)}
    i = 1
    while f"Note {i}" in existing_titles:
        i += 1
    return f"Note {i}"


def title_from_filename(filename):
    return os.path.splitext(filename)[0]


def read_note(notes_dir, filename):
    path = os.path.join(notes_dir, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_note_atomic(notes_dir, filename, content):
    os.makedirs(notes_dir, exist_ok=True)
    path = os.path.join(notes_dir, filename)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)


def create_note(notes_dir, title=None):
    os.makedirs(notes_dir, exist_ok=True)
    title = (title or "").strip() or next_default_name(notes_dir)
    filename = slugify_filename(title) + ".txt"
    path = os.path.join(notes_dir, filename)
    if not os.path.exists(path):
        write_note_atomic(notes_dir, filename, "")
    return filename


def rename_note(notes_dir, old_filename, new_title):
    new_title = (new_title or "").strip()
    if not new_title:
        return old_filename
    new_filename = slugify_filename(new_title) + ".txt"
    if new_filename == old_filename:
        return old_filename
    old_path = os.path.join(notes_dir, old_filename)
    new_path = os.path.join(notes_dir, new_filename)
    if os.path.exists(new_path):
        return old_filename  # name collision — leave the old file alone
    if os.path.exists(old_path):
        os.replace(old_path, new_path)
    return new_filename


def delete_note(notes_dir, filename):
    path = os.path.join(notes_dir, filename)
    if os.path.exists(path):
        os.remove(path)


def search_notes(notes_dir, query):
    """Filenames + contents, across all notes."""
    query = query.lower().strip()
    if not query:
        return list_note_files(notes_dir)
    matches = []
    for filename in list_note_files(notes_dir):
        title = title_from_filename(filename)
        if query in title.lower():
            matches.append(filename)
            continue
        if query in read_note(notes_dir, filename).lower():
            matches.append(filename)
    return matches
