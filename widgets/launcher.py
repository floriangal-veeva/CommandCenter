"""App & Link Launcher — tiled icon grid read from config.json's
launcher_items, plus a '+ Add' modal that appends new entries."""

import os
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from widgets.icons import (
    get_icon_image,
    fetch_favicon_image,
    load_custom_icon_image,
    search_bundled_icons,
)
from themes import contrasting_text_color

TILE_COLUMNS = 3
ICON_SIZE = 36
PICKER_COLUMNS = 4
PICKER_SEARCH_DEBOUNCE_MS = 250
ICON_FILETYPES = [
    ("Icon/image files", "*.ico *.png *.jpg *.jpeg *.bmp *.gif *.svg"),
    ("All files", "*.*"),
]


class LauncherWidget(ctk.CTkFrame):
    def __init__(self, master, config_store, config, event_queue, ui_font="Segoe UI"):
        super().__init__(master, corner_radius=8)
        self.config_store = config_store
        self.config = config
        self.event_queue = event_queue
        self.ui_font = ui_font
        self._favicon_cache = {}
        self._fetching_favicons = set()

        self.title_label = ctk.CTkLabel(
            self, text="App & Link Launcher", anchor="w", font=(self.ui_font, 13, "bold")
        )
        self.title_label.pack(fill="x", padx=12, pady=(10, 6))

        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="x", padx=12, pady=(0, 6))
        for col in range(TILE_COLUMNS):
            self.grid_frame.grid_columnconfigure(col, weight=1, uniform="tile")

        self.add_button = ctk.CTkButton(self, text="+ Add", width=70, command=self._open_add_modal)
        self.add_button.pack(padx=12, pady=(0, 10), anchor="e")

        self.item_buttons = []
        self._render_items()

    def _render_items(self):
        for b in self.item_buttons:
            b.destroy()
        self.item_buttons = []
        items = self.config.get("launcher_items", [])
        for idx, item in enumerate(items):
            row, col = divmod(idx, TILE_COLUMNS)
            target = item.get("target", "")
            icon_path = item.get("icon_path", "")
            is_url = target.lower().startswith(("http://", "https://"))

            icon = load_custom_icon_image(icon_path, size=ICON_SIZE) if icon_path else None
            if icon is None and is_url:
                icon = self._favicon_cache.get(target)
            if icon is None:
                icon = get_icon_image(target, size=ICON_SIZE) if target else None

            btn = ctk.CTkButton(
                self.grid_frame,
                text=item.get("label", "?"),
                image=icon,
                compound="top",
                font=(self.ui_font, 11),
                width=74,
                height=68,
                command=lambda t=target: self._launch(t),
            )
            btn.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            self._bind_context_menu(btn, idx)
            self.item_buttons.append(btn)

            if icon_path:
                continue  # user-selected icon wins; skip auto favicon fetch
            if is_url and target not in self._favicon_cache and target not in self._fetching_favicons:
                self._fetching_favicons.add(target)
                threading.Thread(target=self._fetch_favicon_worker, args=(target,), daemon=True).start()

    def _fetch_favicon_worker(self, target):
        image = fetch_favicon_image(target, size=ICON_SIZE)
        self._fetching_favicons.discard(target)
        if image is not None:
            self._favicon_cache[target] = image
            self.event_queue.put(lambda: self._apply_fetched_icon(target, image))

    def _apply_fetched_icon(self, target, image):
        for idx, item in enumerate(self.config.get("launcher_items", [])):
            if item.get("target") == target and idx < len(self.item_buttons):
                self.item_buttons[idx].configure(image=image)

    def _bind_context_menu(self, widget, idx):
        """CTkButton is a Frame wrapping an inner Canvas + Label — a click
        almost always lands on one of those children, which don't forward
        events to the outer widget's bindings. Bind recursively so
        right-click actually fires regardless of which child was hit."""
        widget.bind("<Button-3>", lambda e, i=idx: self._open_item_context_menu(e, i))
        for child in widget.winfo_children():
            self._bind_context_menu(child, idx)

    def _open_item_context_menu(self, event, idx):
        items = self.config.get("launcher_items", [])
        if idx >= len(items):
            return
        item = items[idx]
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Change Icon...", command=lambda: self._choose_icon_for_item(idx))
        menu.add_command(
            label="Pick from Icon Library...", command=lambda: self._pick_icon_from_library_for_item(idx)
        )
        if item.get("icon_path"):
            menu.add_command(label="Clear Custom Icon", command=lambda: self._clear_icon_for_item(idx))
        menu.add_separator()
        menu.add_command(label="Remove", command=lambda: self._remove_item(idx))
        menu.tk_popup(event.x_root, event.y_root)

    def _choose_icon_for_item(self, idx):
        path = filedialog.askopenfilename(parent=self, filetypes=ICON_FILETYPES)
        if not path:
            return
        items = self.config.get("launcher_items", [])
        if idx >= len(items):
            return
        items[idx]["icon_path"] = path
        self.config_store.write(self.config)
        self._render_items()
        if self._theme:
            self.apply_theme(self._theme)

    def _pick_icon_from_library_for_item(self, idx):
        def on_select(path):
            items = self.config.get("launcher_items", [])
            if idx >= len(items):
                return
            items[idx]["icon_path"] = path
            self.config_store.write(self.config)
            self._render_items()
            if self._theme:
                self.apply_theme(self._theme)

        self._open_icon_picker(on_select)

    def _open_icon_picker(self, on_select):
        """Searchable grid over the local icons/ folder (e.g. Lucide),
        keyed on filename + the matching .json's tags/categories. Fully
        offline — no network call, no third-party icon API."""
        theme = self._theme or {}
        modal = ctk.CTkToplevel(self)
        modal.title("Choose Icon")
        modal.geometry("480x540")
        modal.grab_set()
        if theme:
            modal.configure(fg_color=theme["surface"])

        search_entry = ctk.CTkEntry(modal, placeholder_text="Search icons (e.g. 'mail', 'folder')...")
        search_entry.pack(fill="x", padx=12, pady=(12, 6))

        results_frame = ctk.CTkScrollableFrame(modal, fg_color="transparent")
        results_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for col in range(PICKER_COLUMNS):
            results_frame.grid_columnconfigure(col, weight=1, uniform="pick")

        state = {"after_id": None}

        def choose(path):
            on_select(path)
            modal.destroy()

        def render_results():
            for child in results_frame.winfo_children():
                child.destroy()
            results = search_bundled_icons(search_entry.get(), limit=48)
            if not results:
                message = "No matches." if search_entry.get().strip() else "No icons found in the icons/ folder."
                ctk.CTkLabel(results_frame, text=message).grid(row=0, column=0, columnspan=PICKER_COLUMNS, pady=20)
                return
            for i, item in enumerate(results):
                row, col = divmod(i, PICKER_COLUMNS)
                icon = load_custom_icon_image(item["path"], size=32)
                btn = ctk.CTkButton(
                    results_frame, text=item["name"], image=icon, compound="top",
                    width=100, height=72, font=(self.ui_font, 9),
                    command=lambda p=item["path"]: choose(p),
                )
                btn.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")

        def on_search_changed(event=None):
            if state["after_id"] is not None:
                modal.after_cancel(state["after_id"])
            state["after_id"] = modal.after(PICKER_SEARCH_DEBOUNCE_MS, render_results)

        search_entry.bind("<KeyRelease>", on_search_changed)
        render_results()

    def _clear_icon_for_item(self, idx):
        items = self.config.get("launcher_items", [])
        if idx >= len(items):
            return
        items[idx].pop("icon_path", None)
        self.config_store.write(self.config)
        self._render_items()
        if self._theme:
            self.apply_theme(self._theme)

    def _remove_item(self, idx):
        items = self.config.get("launcher_items", [])
        if idx >= len(items):
            return
        del items[idx]
        self.config_store.write(self.config)
        self._render_items()
        if self._theme:
            self.apply_theme(self._theme)

    def _launch(self, target):
        if not target:
            return
        try:
            os.startfile(target)
        except OSError as e:
            print(f"[launcher] failed to launch {target!r}: {e}")

    def _open_add_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Add Launcher Item")
        modal.geometry("360x320")
        modal.grab_set()

        ctk.CTkLabel(modal, text="Label").pack(anchor="w", padx=16, pady=(16, 0))
        label_entry = ctk.CTkEntry(modal)
        label_entry.pack(fill="x", padx=16)

        ctk.CTkLabel(modal, text="Target (exe path or URL)").pack(anchor="w", padx=16, pady=(12, 0))
        target_entry = ctk.CTkEntry(modal)
        target_entry.pack(fill="x", padx=16)

        def browse_target():
            path = filedialog.askopenfilename(parent=modal)
            if path:
                target_entry.delete(0, "end")
                target_entry.insert(0, path)

        target_browse_row = ctk.CTkFrame(modal, fg_color="transparent")
        target_browse_row.pack(fill="x", padx=16, pady=(4, 0))
        ctk.CTkButton(target_browse_row, text="Browse...", width=90, command=browse_target).pack(side="left")

        ctk.CTkLabel(modal, text="Icon (optional — pick your own instead of the auto one)").pack(
            anchor="w", padx=16, pady=(12, 0)
        )
        icon_row = ctk.CTkFrame(modal, fg_color="transparent")
        icon_row.pack(fill="x", padx=16)
        icon_path_entry = ctk.CTkEntry(icon_row)
        icon_path_entry.pack(side="left", fill="x", expand=True)

        def browse_icon():
            path = filedialog.askopenfilename(parent=modal, filetypes=ICON_FILETYPES)
            if path:
                icon_path_entry.delete(0, "end")
                icon_path_entry.insert(0, path)

        ctk.CTkButton(icon_row, text="Browse...", width=90, command=browse_icon).pack(side="left", padx=(6, 0))

        def set_icon_path(path):
            icon_path_entry.delete(0, "end")
            icon_path_entry.insert(0, path)

        ctk.CTkButton(
            modal, text="Pick from Icon Library...", command=lambda: self._open_icon_picker(set_icon_path)
        ).pack(fill="x", padx=16, pady=(6, 0))

        button_row = ctk.CTkFrame(modal, fg_color="transparent")
        button_row.pack(fill="x", padx=16, pady=16)

        def submit():
            label = label_entry.get().strip()
            target = target_entry.get().strip()
            icon_path = icon_path_entry.get().strip()
            if not label or not target:
                return
            new_item = {"label": label, "target": target}
            if icon_path:
                new_item["icon_path"] = icon_path
            items = self.config.setdefault("launcher_items", [])
            items.append(new_item)
            self.config_store.write(self.config)
            self._render_items()
            if self._theme:
                self.apply_theme(self._theme)
            modal.destroy()

        ctk.CTkButton(button_row, text="Add", width=90, command=submit).pack(side="right")
        ctk.CTkButton(button_row, text="Cancel", width=90, command=modal.destroy).pack(side="right", padx=8)

    _theme = None

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(fg_color=theme["surface"], border_color=theme["border"], border_width=1)
        self.title_label.configure(text_color=theme["text"])
        for btn in self.item_buttons:
            btn.configure(
                fg_color=theme["background"],
                hover_color=theme["border"],
                text_color=theme["text"],
                border_color=theme["border"],
                border_width=1,
            )
        self.add_button.configure(
            fg_color=theme["tertiary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["tertiary"]),
        )

    def apply_ui_font(self, family):
        self.ui_font = family
        self.title_label.configure(font=(family, 13, "bold"))
        for btn in self.item_buttons:
            btn.configure(font=(family, 11))
