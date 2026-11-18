"""Command Center — main entry point.
Part 1: app shell, theming, fonts, 3-column Bento grid with placeholder cards.
Part 2: App & Link Launcher, Mini-CMD Terminal (Vault Login button dropped
per user request — not being built).
Part 3: Daily Top 3, VEEV Stock Chart.
Part 4: News.
Part 5: Notes — a permanent card in the center column of the Bento grid,
under the App & Link Launcher (not a separate OS window or a toggled page).
Part 6: System tray (hide-on-X, Show/Refresh/Quit), auto-refresh wiring.
Part 7: Billable Hours Logger.
"""

import os
import sys
import threading

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# pythonw.exe gives sys.stdout/stderr = None. Redirect before anything else
# runs, so an uncaught print()/log line never crashes with AttributeError.
_log_path = os.path.join(LOG_DIR, "app.log")
_log_file = open(_log_path, "a", buffering=1, encoding="utf-8")
sys.stdout = _log_file
sys.stderr = _log_file

import datetime
import queue

import customtkinter as ctk

import fonts
from storage import AtomicJSONStore
from themes import ThemeManager, contrasting_text_color
from widgets.launcher import LauncherWidget
from widgets.mini_cmd import MiniCmdWidget
from widgets.top3 import Top3Widget
from widgets.stock_chart import StockChartWidget
from widgets.news import NewsWidget
from widgets.notes.notes_page import NotesPage
from widgets.billable import BillableWidget

CONFIG_PATH = os.path.join(APP_DIR, "config.json")
STATE_PATH = os.path.join(APP_DIR, "state.json")
NOTES_DIR = os.path.join(APP_DIR, "notes")
TIMESHEETS_DIR = os.path.join(APP_DIR, "timesheets")
TOP3_HISTORY_PATH = os.path.join(APP_DIR, "top3_history.txt")

REFRESH_HOURS = (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22)


class CommandCenterApp:
    def __init__(self):
        self.config_store = AtomicJSONStore(CONFIG_PATH, default={})
        self.state_store = AtomicJSONStore(STATE_PATH, default={})
        self.config = self.config_store.read()
        self.state = self.state_store.read()

        self.event_queue = queue.Queue()
        self.theme_manager = ThemeManager()
        self._tray_icon = None

        ctk.set_appearance_mode("dark")
        # Stops CTk's automatic per-monitor DPI rescaling, which fades the
        # whole window out and back in (alpha 0.15 -> 1) while it tears down
        # and rebuilds every widget's size/fonts whenever the window crosses
        # onto a monitor with a different display scaling — the visible
        # "weird rerendering" when dragging the window across monitors.
        ctk.deactivate_automatic_dpi_awareness()
        self.root = ctk.CTk()
        self.root.title("Command Center")
        self.root.geometry(self._initial_geometry())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        icon_path = os.path.join(APP_DIR, "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception as e:
                print(f"[main] failed to set window icon: {e}")

        self._all_fonts = fonts.list_all_fonts()
        self._mono_fonts = fonts.list_monospace_fonts()

        self._build_layout()
        self._apply_initial_theme_and_fonts()

        self._setup_hotkey_placeholder()
        self._setup_tray()
        self._schedule_next_auto_refresh()
        self._tick_clock()
        self._drain_event_queue()
        self.root.after(200, self.refresh_all)  # boot refresh, per spec §4

    # ---------- layout ----------

    def _initial_geometry(self):
        w = self.state.get("window", {}).get("width", 1280)
        h = self.state.get("window", {}).get("height", 800)
        return f"{w}x{h}"

    def _build_layout(self):
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_columns()

    def _build_header(self):
        header = ctk.CTkFrame(self.root, corner_radius=0, height=56)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(2, weight=1)
        self.header = header

        # Thin accent strip tied to the theme's "primary" role, so a theme
        # switch is unmistakable even when "surface" is close to "background".
        self.header_accent = ctk.CTkFrame(self.root, corner_radius=0, height=3)
        self.header_accent.grid(row=1, column=0, sticky="ew")

        self.title_label = ctk.CTkLabel(header, text="COMMAND CENTER", font=("Segoe UI", 16, "bold"))
        self.title_label.grid(row=0, column=0, padx=(16, 24), pady=12)

        self.clock_label = ctk.CTkLabel(header, text="--:--:--", font=("Segoe UI", 13))
        self.clock_label.grid(row=0, column=1, padx=8)

        self.updated_label = ctk.CTkLabel(header, text="Updated --:--", font=("Segoe UI", 11))
        self.updated_label.grid(row=0, column=3, padx=8)

        self.refresh_button = ctk.CTkButton(header, text="Refresh", width=80, command=self.refresh_all)
        self.refresh_button.grid(row=0, column=4, padx=8)

        self.display_button = ctk.CTkButton(
            header, text="Theme & Font", width=110, command=self._open_display_settings
        )
        self.display_button.grid(row=0, column=5, padx=(8, 16))

    def _build_columns(self):
        body = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        for col in range(3):
            body.grid_columnconfigure(col, weight=1, uniform="col")
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color="transparent")
        center = ctk.CTkFrame(body, fg_color="transparent")
        right = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        center.grid(row=0, column=1, sticky="nsew", padx=6)
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        self.themed_widgets = []
        self.ui_font_widgets = []
        self.mono_font_widgets = []
        self.refreshable_widgets = []

        ui_font = self.config.get("ui_font", "Segoe UI")
        mono_font = self.config.get("mono_font", "Consolas")

        # Left column: Top 3, Billable Hours, Mini-CMD (expands to fill remaining height)
        self.top3_widget = Top3Widget(left, self.state_store, self.state, TOP3_HISTORY_PATH, ui_font=ui_font)
        self.top3_widget.pack(fill="x", pady=(0, 8))
        self.theme_manager.register(self.top3_widget)
        self.ui_font_widgets.append(self.top3_widget)
        self.refreshable_widgets.append(self.top3_widget)

        self.billable_widget = BillableWidget(
            left, self.config_store, self.config, TIMESHEETS_DIR, ui_font=ui_font
        )
        self.billable_widget.pack(fill="x", pady=(0, 8))
        self.theme_manager.register(self.billable_widget)
        self.ui_font_widgets.append(self.billable_widget)

        self.mini_cmd_widget = MiniCmdWidget(
            left, self.event_queue, self.state_store, self.state, mono_font=mono_font
        )
        self.mini_cmd_widget.pack(fill="both", expand=True, pady=(0, 8))
        self.theme_manager.register(self.mini_cmd_widget)
        self.mono_font_widgets.append(self.mini_cmd_widget)

        # Center column: App & Link Launcher, Notes (expands to fill remaining height)
        self.launcher_widget = LauncherWidget(
            center, self.config_store, self.config, self.event_queue, ui_font=ui_font
        )
        self.launcher_widget.pack(fill="x", pady=(0, 8))
        self.theme_manager.register(self.launcher_widget)
        self.ui_font_widgets.append(self.launcher_widget)

        self.notes_page = NotesPage(center, NOTES_DIR, mono_font=mono_font, ui_font=ui_font)
        self.notes_page.pack(fill="both", expand=True, pady=(0, 8))
        self.theme_manager.register(self.notes_page)
        self.ui_font_widgets.append(self.notes_page)
        self.mono_font_widgets.append(self.notes_page)
        self.refreshable_widgets.append(self.notes_page)

        # Right column: VEEV Stock Chart, News (expands to fill remaining height)
        self.stock_chart_widget = StockChartWidget(right, self.event_queue)
        self.stock_chart_widget.pack(fill="x", pady=(0, 8))
        self.theme_manager.register(self.stock_chart_widget)
        self.refreshable_widgets.append(self.stock_chart_widget)

        self.news_widget = NewsWidget(right, self.event_queue, self.config_store, self.config, ui_font=ui_font)
        self.news_widget.pack(fill="both", expand=True, pady=(0, 8))
        self.theme_manager.register(self.news_widget)
        self.ui_font_widgets.append(self.news_widget)
        self.refreshable_widgets.append(self.news_widget)

    # ---------- theming / fonts ----------

    def _apply_initial_theme_and_fonts(self):
        theme_name = self.config.get("theme", self.theme_manager.theme_names()[0])
        self.theme_manager.apply(theme_name)
        self._apply_header_theme(self.theme_manager.get_theme(theme_name))

    def _apply_header_theme(self, theme):
        self.header.configure(fg_color=theme["surface"])
        self.header_accent.configure(fg_color=theme["primary"])
        self.root.configure(fg_color=theme["background"])
        for label in (self.title_label, self.clock_label, self.updated_label):
            label.configure(text_color=theme["text"])
        self.refresh_button.configure(
            fg_color=theme["primary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["primary"]),
        )
        self.display_button.configure(
            fg_color=theme["tertiary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["tertiary"]),
        )
        self._set_titlebar_colors(theme)

    def _set_titlebar_colors(self, theme):
        """Colors the native Windows title bar — the strip with the
        minimize/maximize/close buttons — which ctk/tkinter can't theme
        directly. Uses DWM's caption/text-color attributes (Windows 11
        build 22000+ only); no-ops silently everywhere else, same
        offline/best-effort pattern as the rest of the app."""
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

            def to_colorref(hex_color):
                hex_color = hex_color.lstrip("#")
                r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
                return r | (g << 8) | (b << 16)

            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36
            caption = ctypes.c_int(to_colorref(theme["surface"]))
            text = ctypes.c_int(to_colorref(theme["text"]))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption)
            )
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text)
            )
        except Exception as e:
            print(f"[main] failed to set titlebar colors (needs Windows 11 22000+): {e}")

    def _open_display_settings(self):
        theme = self.theme_manager.get_theme(self.config.get("theme", self.theme_manager.theme_names()[0]))

        modal = ctk.CTkToplevel(self.root)
        modal.title("Theme & Font")
        modal.geometry("300x380")
        modal.grab_set()
        modal.configure(fg_color=theme["surface"])

        def add_row(label_text, values, current, on_change):
            ctk.CTkLabel(modal, text=label_text, anchor="w", text_color=theme["text"]).pack(
                fill="x", padx=16, pady=(14, 2)
            )
            dropdown = ctk.CTkOptionMenu(modal, values=values, command=on_change)
            if current in values:
                dropdown.set(current)
            dropdown.pack(fill="x", padx=16)

        add_row("Theme", self.theme_manager.theme_names(), self.config.get("theme"), self.on_theme_changed)
        add_row("UI Font", self._all_fonts, self.config.get("ui_font", "Segoe UI"), self.on_ui_font_changed)
        add_row("Mono Font", self._mono_fonts, self.config.get("mono_font", "Consolas"), self.on_mono_font_changed)

        ctk.CTkButton(
            modal, text="Edit Current Theme", fg_color=theme["tertiary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["tertiary"]),
            command=lambda: self._open_add_theme_modal(
                modal, edit_name=self.config.get("theme", self.theme_manager.theme_names()[0])
            ),
        ).pack(pady=(20, 4))
        ctk.CTkButton(
            modal, text="+ Add Theme", fg_color=theme["tertiary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["tertiary"]),
            command=lambda: self._open_add_theme_modal(modal),
        ).pack(pady=4)
        ctk.CTkButton(modal, text="Close", command=modal.destroy).pack(pady=4)

    def _open_add_theme_modal(self, parent_modal=None, edit_name=None):
        from themes import ALL_ROLES
        from tkinter import colorchooser

        theme = self.theme_manager.get_theme(edit_name or self.config.get("theme", self.theme_manager.theme_names()[0]))

        modal = ctk.CTkToplevel(self.root)
        modal.title("Edit Theme" if edit_name else "Add Theme")
        modal.geometry("340x520")
        modal.grab_set()
        modal.configure(fg_color=theme["surface"])

        ctk.CTkLabel(modal, text="Theme Name", anchor="w", text_color=theme["text"]).pack(
            fill="x", padx=16, pady=(16, 2)
        )
        name_entry = ctk.CTkEntry(modal)
        if edit_name:
            name_entry.insert(0, edit_name)
        name_entry.pack(fill="x", padx=16)

        scroll = ctk.CTkScrollableFrame(modal, fg_color="transparent", height=320)
        scroll.pack(fill="both", expand=True, padx=16, pady=(10, 10))

        colors = dict(theme)

        def pick_color(role, swatch):
            _, hex_color = colorchooser.askcolor(color=colors.get(role), parent=modal)
            if hex_color:
                colors[role] = hex_color
                swatch.configure(fg_color=hex_color)

        for role in ALL_ROLES:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=role, width=90, anchor="w", text_color=theme["text"]).pack(side="left")
            swatch = ctk.CTkButton(row, text="", width=60, fg_color=colors.get(role, "#888888"))
            swatch.configure(command=lambda r=role, b=swatch: pick_color(r, b))
            swatch.pack(side="left", padx=8)

        def save():
            name = name_entry.get().strip()
            if not name:
                return
            self.theme_manager.save_theme(name, colors)
            self.on_theme_changed(name)
            modal.destroy()
            if parent_modal is not None:
                parent_modal.destroy()
            self._open_display_settings()

        ctk.CTkButton(modal, text="Save Theme", command=save).pack(pady=12)

    def on_theme_changed(self, name):
        theme = self.theme_manager.apply(name)
        self._apply_header_theme(theme)
        self.config["theme"] = name
        self.config_store.write(self.config)

    def on_ui_font_changed(self, family):
        self.config["ui_font"] = family
        self.config_store.write(self.config)
        for widget in self.ui_font_widgets:
            widget.apply_ui_font(family)

    def on_mono_font_changed(self, family):
        self.config["mono_font"] = family
        self.config_store.write(self.config)
        for widget in self.mono_font_widgets:
            widget.apply_mono_font(family)

    # ---------- system tray ----------

    def _setup_tray(self):
        import pystray
        from PIL import Image, ImageDraw

        def make_icon_image():
            icon_path = os.path.join(APP_DIR, "app_icon.ico")
            if os.path.exists(icon_path):
                return Image.open(icon_path).convert("RGBA").resize((64, 64), Image.LANCZOS)
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([4, 4, 60, 60], radius=14, fill="#38BDF8")
            draw.text((14, 22), "CC", fill="#0B111A")
            return img

        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda: self.root.after(0, self._show_window), default=True),
            pystray.MenuItem("Refresh", lambda: self.root.after(0, self.refresh_all)),
            pystray.MenuItem("Quit", lambda: self.root.after(0, self._quit_app)),
        )
        try:
            self._tray_icon = pystray.Icon("command_center", make_icon_image(), "Command Center", menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"[main] tray setup failed: {e}")
            self._tray_icon = None

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit_app(self):
        self.notes_page.flush_pending_save()
        self._persist_window_state()
        if self._tray_icon is not None:
            self._tray_icon.stop()
        self.root.destroy()

    # ---------- clock / refresh ----------

    def _tick_clock(self):
        now = datetime.datetime.now()
        self.clock_label.configure(text=now.strftime("%H:%M:%S  %Y-%m-%d"))
        self.root.after(1000, self._tick_clock)

    def refresh_all(self):
        for widget in getattr(self, "refreshable_widgets", []):
            widget.refresh()
        now = datetime.datetime.now()
        self.updated_label.configure(text=f"Updated {now.strftime('%H:%M')}")

    def _schedule_next_auto_refresh(self):
        now = datetime.datetime.now()
        candidates = []
        for h in REFRESH_HOURS:
            candidates.append(now.replace(hour=h, minute=1, second=0, microsecond=0))
        candidates.append((now.replace(hour=0, minute=1, second=0, microsecond=0) + datetime.timedelta(days=1)))
        next_time = min(c for c in candidates if c > now)
        delay_ms = int((next_time - now).total_seconds() * 1000)
        self.root.after(delay_ms, self._auto_refresh_fired)

    def _auto_refresh_fired(self):
        self.refresh_all()
        self._schedule_next_auto_refresh()

    # ---------- background-thread event queue ----------

    def _drain_event_queue(self):
        try:
            while True:
                callback = self.event_queue.get_nowait()
                callback()
        except queue.Empty:
            pass
        self.root.after(50, self._drain_event_queue)

    # ---------- deferred features (placeholders only, per spec §3) ----------

    def _setup_hotkey_placeholder(self):
        """Global hotkey is deferred pending IT/Security sign-off.
        Future approach: ctypes-based Win32 RegisterHotKey (WM_HOTKEY message
        loop), registered/unregistered via user32.dll. Do NOT use the
        `keyboard` library (global low-level hook) even as a placeholder."""
        pass

    # ---------- lifecycle ----------

    def _persist_window_state(self):
        win = self.root.winfo_geometry()
        try:
            dims, x, y = win.split("+")
            w, h = dims.split("x")
            self.state["window"] = {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
            self.state_store.write(self.state)
        except Exception as e:
            print(f"[main] failed to persist window geometry: {e}")

    def on_close(self):
        # Clicking X hides to the system tray instead of quitting (spec §4).
        # Real quit is only via the tray menu's Quit item -> _quit_app.
        self.notes_page.flush_pending_save()
        self._persist_window_state()
        self.root.withdraw()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = CommandCenterApp()
    app.run()
