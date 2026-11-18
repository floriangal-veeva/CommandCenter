"""Notes — a permanent card in the Bento grid (center column, under the
launcher), not a separate OS window. One .txt file per note. Search bar
covers all notes (filenames + contents). Autosave debounced ~600ms via the
same atomic-write pattern as everything else."""

import os
import tkinter as tk

import customtkinter as ctk

from widgets.notes import note_store
from themes import contrasting_text_color

AUTOSAVE_DEBOUNCE_MS = 600
LIST_PANEL_WIDTH = 130


class NotesPage(ctk.CTkFrame):
    def __init__(self, master, notes_dir, mono_font="Consolas", ui_font="Segoe UI"):
        super().__init__(master, corner_radius=8)
        self.notes_dir = notes_dir
        self.mono_font = mono_font
        self.ui_font = ui_font
        self._save_after_id = None
        self.current_filename = None
        self._theme = {}
        self.note_buttons = {}

        header_row = ctk.CTkFrame(self, fg_color="transparent")
        header_row.pack(fill="x", padx=12, pady=(10, 6))
        self.title_label = ctk.CTkLabel(
            header_row, text="Notes", anchor="w", font=(self.ui_font, 13, "bold")
        )
        self.title_label.pack(side="left")
        self.folder_button = ctk.CTkButton(
            header_row, text="\U0001F4C2", width=28, command=self._open_folder
        )
        self.folder_button.pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(body, width=LIST_PANEL_WIDTH, corner_radius=6)
        self.left_panel.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        self.left_panel.grid_propagate(False)

        self.search_entry = ctk.CTkEntry(self.left_panel, placeholder_text="Search...")
        self.search_entry.pack(fill="x", padx=6, pady=(6, 4))
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        self.new_button = ctk.CTkButton(self.left_panel, text="+ New", height=24, command=self._on_new_note)
        self.new_button.pack(fill="x", padx=6, pady=(0, 6))

        self.note_list_frame = ctk.CTkScrollableFrame(self.left_panel, fg_color="transparent")
        self.note_list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        self.right_panel = ctk.CTkFrame(body, corner_radius=6)
        self.right_panel.grid(row=0, column=1, sticky="nsew")

        self.title_entry = ctk.CTkEntry(self.right_panel, font=(self.mono_font, 12))
        self.title_entry.pack(fill="x", padx=8, pady=(8, 4))
        self.title_entry.bind("<Return>", self._on_title_committed)
        self.title_entry.bind("<FocusOut>", self._on_title_committed)

        self.editor = ctk.CTkTextbox(self.right_panel, font=(self.mono_font, 12), wrap="word")
        self.editor.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.editor.bind("<KeyRelease>", self._on_editor_changed)

        self._refresh_note_list()
        self._load_or_create_initial_note()

    # ---------- list ----------

    def _refresh_note_list(self, filter_query=""):
        for child in self.note_list_frame.winfo_children():
            child.destroy()
        self.note_buttons = {}

        filenames = (
            note_store.search_notes(self.notes_dir, filter_query)
            if filter_query
            else note_store.list_note_files(self.notes_dir)
        )
        for filename in filenames:
            title = note_store.title_from_filename(filename)
            btn = ctk.CTkButton(
                self.note_list_frame, text=title, anchor="w", height=24, font=(self.ui_font, 11),
                command=lambda f=filename: self._open_note(f),
            )
            btn.pack(fill="x", pady=1)
            self._bind_context_menu(btn, filename)
            self.note_buttons[filename] = btn
        self._update_list_styles()

    def _bind_context_menu(self, widget, filename):
        """CTkButton is a Frame wrapping an inner Canvas + Label — a click
        almost always lands on one of those children, which don't forward
        events to the outer widget's bindings. Bind recursively so
        right-click actually fires regardless of which child was hit."""
        widget.bind("<Button-3>", lambda e, f=filename: self._open_note_context_menu(e, f))
        for child in widget.winfo_children():
            self._bind_context_menu(child, filename)

    def _open_note_context_menu(self, event, filename):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Delete", command=lambda: self._delete_note(filename))
        menu.tk_popup(event.x_root, event.y_root)

    def _delete_note(self, filename):
        if self._save_after_id is not None and self.current_filename == filename:
            self.after_cancel(self._save_after_id)
            self._save_after_id = None
        note_store.delete_note(self.notes_dir, filename)
        if self.current_filename == filename:
            self.current_filename = None
        self._refresh_note_list(self.search_entry.get())
        if self.current_filename is None:
            self._load_or_create_initial_note()

    def _on_search_changed(self, event=None):
        self._refresh_note_list(self.search_entry.get())

    def _load_or_create_initial_note(self):
        files = note_store.list_note_files(self.notes_dir)
        if not files:
            filename = note_store.create_note(self.notes_dir)
            self._refresh_note_list()
        else:
            filename = files[0]
        self._open_note(filename)

    def refresh(self):
        """Picks up notes added/removed directly on disk (e.g. via the
        folder button, then deleting a file in Explorer) — not just
        changes made from inside the app. Hooked into the app's manual
        Refresh button + 2-hour auto-refresh scheduler."""
        deleted_externally = self.current_filename is not None and not os.path.exists(
            os.path.join(self.notes_dir, self.current_filename)
        )
        if deleted_externally:
            # Don't flush a pending autosave for a file that's gone —
            # that would just silently recreate it.
            if self._save_after_id is not None:
                self.after_cancel(self._save_after_id)
                self._save_after_id = None
            self.current_filename = None
        self._refresh_note_list(self.search_entry.get())
        if deleted_externally:
            self._load_or_create_initial_note()

    def _open_folder(self):
        try:
            os.startfile(self.notes_dir)
        except OSError as e:
            print(f"[notes] failed to open folder: {e}")

    def _on_new_note(self):
        filename = note_store.create_note(self.notes_dir)
        self.search_entry.delete(0, "end")
        self._refresh_note_list()
        self._open_note(filename)

    # ---------- editing ----------

    def _open_note(self, filename):
        if self.current_filename and self.current_filename != filename:
            self.flush_pending_save()
        self.current_filename = filename
        title = note_store.title_from_filename(filename)
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, title)

        content = note_store.read_note(self.notes_dir, filename)
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self._update_list_styles()

    def _on_title_committed(self, event=None):
        if not self.current_filename:
            return
        new_title = self.title_entry.get().strip()
        if not new_title:
            return
        new_filename = note_store.rename_note(self.notes_dir, self.current_filename, new_title)
        if new_filename != self.current_filename:
            self.current_filename = new_filename
            self._refresh_note_list(self.search_entry.get())

    def _on_editor_changed(self, event=None):
        if self._save_after_id is not None:
            self.after_cancel(self._save_after_id)
        self._save_after_id = self.after(AUTOSAVE_DEBOUNCE_MS, self._persist)

    def flush_pending_save(self):
        if self._save_after_id is not None:
            self.after_cancel(self._save_after_id)
            self._save_after_id = None
        self._persist()

    def _persist(self):
        if not self.current_filename:
            return
        content = self.editor.get("1.0", "end-1c")
        note_store.write_note_atomic(self.notes_dir, self.current_filename, content)

    # ---------- styling ----------

    def _update_list_styles(self):
        active = self._theme.get("primary", "#38BDF8")
        inactive = self._theme.get("tertiary", "#777777")
        for filename, btn in self.note_buttons.items():
            btn.configure(fg_color=active if filename == self.current_filename else inactive)

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(fg_color=theme["surface"], border_color=theme["border"], border_width=1)
        self.title_label.configure(text_color=theme["text"])
        self.left_panel.configure(fg_color=theme["background"])
        self.right_panel.configure(fg_color=theme["background"])
        self.note_list_frame.configure(fg_color=theme["background"])
        self.search_entry.configure(
            fg_color=theme["surface"], border_color=theme["border"], text_color=theme["text"]
        )
        self.new_button.configure(
            fg_color=theme["primary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["primary"]),
        )
        self.folder_button.configure(
            fg_color=theme["tertiary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["tertiary"]),
        )
        self.title_entry.configure(
            fg_color=theme["surface"], border_color=theme["border"], text_color=theme["text"]
        )
        self.editor.configure(fg_color=theme["surface"], text_color=theme["text"])
        self._update_list_styles()

    def apply_mono_font(self, family):
        self.mono_font = family
        self.title_entry.configure(font=(family, 12))
        self.editor.configure(font=(family, 12))

    def apply_ui_font(self, family):
        self.ui_font = family
        self.title_label.configure(font=(family, 13, "bold"))
        for btn in self.note_buttons.values():
            btn.configure(font=(family, 11))
