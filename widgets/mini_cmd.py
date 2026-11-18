"""Mini-CMD Terminal — runs whatever the user types, via cmd.exe, in the
tracked cwd. No command allowlist (removed per user request — this is a
personal tool on the user's own machine, run non-interactively with a strict
timeout, not a shared/remote surface). Never used for `vault login` or
anything auth-related — that flow lives entirely in a separate, untouched
cmd.exe window (see widgets/vault_login.py note in spec — intentionally not
built). Command history is in-memory only — state.json persists the cwd,
NOT history (see spec §2/§5a)."""

import os
import subprocess
import threading

import customtkinter as ctk

from themes import contrasting_text_color

TIMEOUT_SECONDS = 15


def _resolve_cd(cwd, arg):
    if not arg:
        return cwd
    candidate = arg if os.path.isabs(arg) else os.path.join(cwd, arg)
    candidate = os.path.normpath(candidate)
    return candidate if os.path.isdir(candidate) else None


class MiniCmdWidget(ctk.CTkFrame):
    def __init__(self, master, event_queue, state_store, state, mono_font="Consolas"):
        super().__init__(master, corner_radius=8)
        self.event_queue = event_queue
        self.state_store = state_store
        self.state = state
        self.mono_font = mono_font
        self.cwd = state.get("mini_cmd_cwd") or os.path.expanduser("~")
        self.history = []
        self.history_index = None

        self.title_label = ctk.CTkLabel(
            self, text="Mini-CMD Terminal", anchor="w", font=("Segoe UI", 13, "bold")
        )
        self.title_label.pack(fill="x", padx=12, pady=(10, 2))

        self.cwd_label = ctk.CTkLabel(
            self, text=self.cwd, anchor="w", font=(self.mono_font, 10), text_color="#999999"
        )
        self.cwd_label.pack(fill="x", padx=12)

        self.output = ctk.CTkTextbox(self, height=90, font=(self.mono_font, 11), wrap="word")
        self.output.pack(fill="both", expand=True, padx=12, pady=(4, 4))
        self.output.configure(state="disabled")

        entry_row = ctk.CTkFrame(self, fg_color="transparent")
        entry_row.pack(fill="x", padx=12, pady=(0, 6))
        self.entry = ctk.CTkEntry(entry_row, font=(self.mono_font, 11), placeholder_text="type a command...")
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Up>", self._on_history_up)
        self.entry.bind("<Down>", self._on_history_down)

        self.run_button = ctk.CTkButton(entry_row, text="Run", width=60, command=self._on_enter)
        self.run_button.pack(side="left", padx=(6, 0))

        bottom_row = ctk.CTkFrame(self, fg_color="transparent")
        bottom_row.pack(fill="x", padx=12, pady=(0, 10))
        self.clear_button = ctk.CTkButton(bottom_row, text="Clear", width=60, command=self._clear_output)
        self.clear_button.pack(side="left")
        self.hint_label = ctk.CTkLabel(
            bottom_row,
            text=f"Runs via cmd.exe · {TIMEOUT_SECONDS}s timeout",
            font=(self.mono_font, 9),
            text_color="#777777",
            anchor="w",
        )
        self.hint_label.pack(side="left", padx=8)

    def _on_enter(self, event=None):
        raw = self.entry.get().strip()
        if not raw:
            return
        self.entry.delete(0, "end")
        self.history.append(raw)
        self.history_index = None
        self._append_output(f"> {raw}")
        self._dispatch(raw)

    def _on_history_up(self, event=None):
        if not self.history:
            return "break"
        if self.history_index is None:
            self.history_index = len(self.history) - 1
        elif self.history_index > 0:
            self.history_index -= 1
        self.entry.delete(0, "end")
        self.entry.insert(0, self.history[self.history_index])
        return "break"

    def _on_history_down(self, event=None):
        if self.history_index is None:
            return "break"
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.entry.delete(0, "end")
            self.entry.insert(0, self.history[self.history_index])
        else:
            self.history_index = None
            self.entry.delete(0, "end")
        return "break"

    def _dispatch(self, raw):
        if raw == "cd" or raw.startswith("cd "):
            arg = raw[2:].strip()
            new_dir = _resolve_cd(self.cwd, arg)
            if new_dir:
                self.cwd = new_dir
                self.cwd_label.configure(text=self.cwd)
                self.state["mini_cmd_cwd"] = self.cwd
                self.state_store.write(self.state)
                self._append_output(self.cwd)
            else:
                self._append_output(f"cd: not found: {arg}")
            return

        threading.Thread(target=self._run_worker, args=(raw,), daemon=True).start()

    def _run_worker(self, raw):
        try:
            result = subprocess.run(
                ["cmd", "/c", raw],
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = (result.stdout or "") + (result.stderr or "")
        except subprocess.TimeoutExpired:
            out = f"[timed out after {TIMEOUT_SECONDS}s]"
        except OSError as e:
            out = f"[error: {e}]"
        self.event_queue.put(lambda: self._append_output(out.rstrip() or "(no output)"))

    def _append_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def _clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def apply_theme(self, theme):
        self.configure(fg_color=theme["surface"], border_color=theme["border"], border_width=1)
        self.title_label.configure(text_color=theme["text"])
        self.cwd_label.configure(text_color=theme["text_muted"])
        self.hint_label.configure(text_color=theme["text_muted"])
        self.output.configure(fg_color=theme["background"], text_color=theme["text"])
        self.entry.configure(fg_color=theme["background"], text_color=theme["text"], border_color=theme["border"])
        self.run_button.configure(
            fg_color=theme["primary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["primary"]),
        )
        self.clear_button.configure(
            fg_color=theme["tertiary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["tertiary"]),
        )

    def apply_mono_font(self, family):
        self.mono_font = family
        self.cwd_label.configure(font=(family, 10))
        self.output.configure(font=(family, 11))
        self.entry.configure(font=(family, 11))
        self.hint_label.configure(font=(family, 9))
