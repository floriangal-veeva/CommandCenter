"""Daily Top 3 — three persistent checkboxes + text fields, saved to
state.json. Checked = overstrike font + dimmed text. An item left unchecked
for 2+ days since it was last written gets a standing danger-colored
highlight, and pops a reminder dialog on every refresh (manual click or the
2-hour auto-refresh tick) until it's checked off or edited."""

import datetime

import customtkinter as ctk

from themes import contrasting_text_color

DEFAULT_ROWS = 3
STALE_AFTER = datetime.timedelta(days=2)


class Top3Widget(ctk.CTkFrame):
    def __init__(self, master, state_store, state, history_path, ui_font="Segoe UI"):
        super().__init__(master, corner_radius=8)
        self.state_store = state_store
        self.state = state
        self.history_path = history_path
        self.ui_font = ui_font
        self._save_after_id = None
        self._theme = {}

        header_row = ctk.CTkFrame(self, fg_color="transparent")
        header_row.pack(fill="x", padx=12, pady=(10, 6))

        self.title_label = ctk.CTkLabel(
            header_row, text="Daily Top 3", anchor="w", font=(self.ui_font, 13, "bold")
        )
        self.title_label.pack(side="left")

        self.clear_button = ctk.CTkButton(
            header_row, text="Clear", width=56, height=22, font=(self.ui_font, 11), command=self._clear_all
        )
        self.clear_button.pack(side="right")

        existing = state.get("top3") or []
        now_iso = datetime.datetime.now().isoformat()
        self.rows = []
        for i in range(DEFAULT_ROWS):
            item = existing[i] if i < len(existing) else {}
            text = item.get("text", "")
            checked = bool(item.get("checked", False))
            updated_at = item.get("updated_at") or now_iso

            row_frame = ctk.CTkFrame(self, fg_color="transparent")
            row_frame.pack(fill="x", padx=12, pady=4)

            var = ctk.BooleanVar(value=checked)
            checkbox = ctk.CTkCheckBox(
                row_frame, text="", width=20, variable=var, command=lambda idx=i: self._on_toggle(idx)
            )
            checkbox.pack(side="left")

            entry = ctk.CTkEntry(row_frame, font=(self.ui_font, 12))
            entry.insert(0, text)
            entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
            entry.bind("<KeyRelease>", lambda e, idx=i: self._on_text_changed(idx))

            self.rows.append(
                {"var": var, "checkbox": checkbox, "entry": entry, "last_text": text, "updated_at": updated_at}
            )

        self._refresh_styles()

    def _persist(self):
        top3 = []
        for row in self.rows:
            text = row["entry"].get()
            if text != row["last_text"]:
                row["updated_at"] = datetime.datetime.now().isoformat()
                row["last_text"] = text
            top3.append({"text": text, "checked": bool(row["var"].get()), "updated_at": row["updated_at"]})
        self.state["top3"] = top3
        self.state_store.write(self.state)
        self._refresh_styles()

    def _on_toggle(self, idx):
        row = self.rows[idx]
        if row["var"].get():
            text = row["entry"].get().strip()
            if text:
                self._append_history(text)
        self._persist()

    def _append_history(self, text):
        """One line per completed task, appended to a single plain-text
        history file: 'task - done date'. Never truncated/rotated — it's
        a running log, not state."""
        try:
            with open(self.history_path, "a", encoding="utf-8") as f:
                f.write(f"{text} - {datetime.date.today().isoformat()}\n")
        except OSError as e:
            print(f"[top3] failed to write history: {e}")

    def _clear_all(self):
        if self._save_after_id is not None:
            self.after_cancel(self._save_after_id)
            self._save_after_id = None
        now_iso = datetime.datetime.now().isoformat()
        for row in self.rows:
            row["entry"].delete(0, "end")
            row["var"].set(False)
            row["last_text"] = ""
            row["updated_at"] = now_iso
        self._persist()

    def _on_text_changed(self, idx):
        if self._save_after_id is not None:
            self.after_cancel(self._save_after_id)
        self._save_after_id = self.after(400, self._persist)

    def _is_stale(self, row):
        text = row["entry"].get().strip()
        if not text or row["var"].get():
            return False
        try:
            updated_at = datetime.datetime.fromisoformat(row["updated_at"])
        except (TypeError, ValueError):
            return False
        return datetime.datetime.now() - updated_at >= STALE_AFTER

    def _refresh_styles(self):
        for row in self.rows:
            entry = row["entry"]
            checked = bool(row["var"].get())
            if checked:
                entry.configure(
                    font=(self.ui_font, 12, "overstrike"),
                    text_color=self._theme.get("text_muted", "#999999"),
                )
            elif self._is_stale(row):
                entry.configure(
                    font=(self.ui_font, 12, "bold"), text_color=self._theme.get("danger", "#F87171")
                )
            else:
                entry.configure(font=(self.ui_font, 12), text_color=self._theme.get("text", "#FFFFFF"))

    def refresh(self):
        """Hooked into the app's manual Refresh button + 2-hour auto-refresh
        scheduler (see main.py's refreshable_widgets)."""
        self._refresh_styles()
        stale_texts = [row["entry"].get().strip() for row in self.rows if self._is_stale(row)]
        if stale_texts:
            self._show_reminder(stale_texts)

    def _show_reminder(self, stale_texts):
        theme = self._theme
        popup = ctk.CTkToplevel(self)
        popup.title("Still open after 2+ days")
        popup.geometry(f"340x{80 + 22 * len(stale_texts)}")
        popup.attributes("-topmost", True)
        popup.configure(fg_color=theme.get("surface", "#111111"))

        ctk.CTkLabel(
            popup,
            text="These Top 3 items are still unchecked:",
            anchor="w",
            font=(self.ui_font, 12, "bold"),
            text_color=theme.get("text", "#FFFFFF"),
        ).pack(fill="x", padx=16, pady=(16, 6))
        for text in stale_texts:
            ctk.CTkLabel(
                popup,
                text=f"• {text}",
                anchor="w",
                font=(self.ui_font, 11),
                text_color=theme.get("danger", "#F87171"),
            ).pack(fill="x", padx=16)
        ctk.CTkButton(popup, text="OK", width=60, command=popup.destroy).pack(pady=12)

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(fg_color=theme["surface"], border_color=theme["border"], border_width=1)
        self.title_label.configure(text_color=theme["text"])
        self.clear_button.configure(
            fg_color=theme["background"],
            hover_color=theme["border"],
            text_color=theme["text"],
            border_color=theme["border"],
            border_width=1,
        )
        for row in self.rows:
            row["checkbox"].configure(
                fg_color=theme["primary"],
                hover_color=theme["secondary"],
                border_color=theme["border"],
                checkmark_color=contrasting_text_color(theme["primary"]),
            )
            row["entry"].configure(fg_color=theme["background"], border_color=theme["border"])
        self._refresh_styles()

    def apply_ui_font(self, family):
        self.ui_font = family
        self.title_label.configure(font=(family, 13, "bold"))
        self.clear_button.configure(font=(family, 11))
        self._refresh_styles()
