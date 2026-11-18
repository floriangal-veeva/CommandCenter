"""VEEV Stock Chart — yfinance + embedded matplotlib figure, themed to match
the active card color. 5H / 5D toggle. Plotted against sequential bar indices
so market closures don't draw flatlines. Hovering the chart shows the exact
price (and timestamp) at that point. Never crashes on network failure —
shows 'Offline / Retrying' in the header instead."""

import concurrent.futures
import threading

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

FETCH_TIMEOUT_SECONDS = 5.0

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2)


class StockChartWidget(ctk.CTkFrame):
    def __init__(self, master, event_queue, ticker="VEEV"):
        super().__init__(master, corner_radius=8)
        self.event_queue = event_queue
        self.ticker = ticker
        self.period_mode = "5H"
        self._theme = {}
        self._last_price = None
        self._last_change_pct = None
        self._times = []
        self._closes = []
        self._annotation = None

        header_row = ctk.CTkFrame(self, fg_color="transparent")
        header_row.pack(fill="x", padx=12, pady=(10, 2))

        self.header_label = ctk.CTkLabel(
            header_row, text=f"{ticker} Loading...", anchor="w", font=("Segoe UI", 13, "bold")
        )
        self.header_label.pack(side="left", fill="x", expand=True)

        self.toggle_5h = ctk.CTkButton(header_row, text="5H", width=36, command=lambda: self._set_mode("5H"))
        self.toggle_5h.pack(side="left", padx=(4, 0))
        self.toggle_5d = ctk.CTkButton(header_row, text="5D", width=36, command=lambda: self._set_mode("5D"))
        self.toggle_5d.pack(side="left", padx=(4, 0))

        self.figure = Figure(figsize=(4, 2.2), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas.mpl_connect("figure_leave_event", self._on_leave)

        self.refresh()

    # ---------- mode toggle ----------

    def _set_mode(self, mode):
        if mode == self.period_mode:
            return
        self.period_mode = mode
        self._update_toggle_styles()
        self.refresh()

    # ---------- fetch (background thread, per spec §2) ----------

    def refresh(self):
        self.header_label.configure(text=f"{self.ticker} Loading...")
        threading.Thread(target=self._fetch_worker, args=(self.period_mode,), daemon=True).start()

    def _fetch_worker(self, mode):
        future = _EXECUTOR.submit(self._fetch_sync, mode)
        try:
            times, closes = future.result(timeout=FETCH_TIMEOUT_SECONDS)
        except Exception as e:
            print(f"[stock_chart] fetch failed: {e}")
            self.event_queue.put(self._show_offline)
            return
        self.event_queue.put(lambda: self._render(times, closes))

    def _fetch_sync(self, mode):
        import yfinance as yf

        ticker = yf.Ticker(self.ticker)
        if mode == "5H":
            hist = ticker.history(period="5d", interval="5m")
            hist = hist.tail(60)
        else:
            hist = ticker.history(period="5d", interval="30m")
        hist = hist.dropna(subset=["Close"])
        closes = hist["Close"].tolist()
        times = hist.index.to_pydatetime().tolist()
        if not closes:
            raise ValueError("no price data returned")
        return times, closes

    # ---------- render (main thread, drained from event_queue) ----------

    def _show_offline(self):
        self.header_label.configure(
            text=f"{self.ticker} Offline / Retrying", text_color=self._theme.get("text_muted", "#999999")
        )

    def _render(self, times, closes):
        self._times = times
        self._closes = closes

        price = closes[-1]
        first = closes[0]
        change_pct = ((price - first) / first * 100) if first else 0.0
        self._last_price = price
        self._last_change_pct = change_pct

        positive = change_pct >= 0
        color = self._theme.get("success", "#4ADE80") if positive else self._theme.get("danger", "#F87171")
        sign = "+" if positive else ""
        self.header_label.configure(
            text=f"{self.ticker} ${price:.2f} ({sign}{change_pct:.2f}%)", text_color=color
        )

        self.ax.clear()
        indices = list(range(len(closes)))
        self.ax.plot(indices, closes, color=color, linewidth=1.5)
        self.ax.set_xticks([])
        self._style_axes()
        self._annotation = self._make_annotation()
        self.canvas.draw_idle()

    def _make_annotation(self):
        theme = self._theme
        annotation = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(12, 12),
            textcoords="offset points",
            fontsize=8,
            color=theme.get("text", "#FFFFFF"),
            bbox=dict(
                boxstyle="round",
                fc=theme.get("background", "#000000"),
                ec=theme.get("border", "#333333"),
            ),
            visible=False,
        )
        return annotation

    def _style_axes(self):
        bg = self._theme.get("surface", "#111111")
        text_color = self._theme.get("text_muted", "#999999")
        border = self._theme.get("border", "#333333")
        self.figure.patch.set_facecolor(bg)
        self.ax.set_facecolor(bg)
        for spine in self.ax.spines.values():
            spine.set_color(border)
        self.ax.tick_params(colors=text_color, labelsize=8)

    def _update_toggle_styles(self):
        active = self._theme.get("primary", "#38BDF8")
        inactive = self._theme.get("tertiary", "#777777")
        self.toggle_5h.configure(fg_color=active if self.period_mode == "5H" else inactive)
        self.toggle_5d.configure(fg_color=active if self.period_mode == "5D" else inactive)

    # ---------- hover tooltip ----------

    def _on_hover(self, event):
        if self._annotation is None or not self._closes:
            return
        if event.inaxes != self.ax or event.xdata is None:
            self._hide_annotation()
            return

        idx = int(round(event.xdata))
        idx = max(0, min(idx, len(self._closes) - 1))
        price = self._closes[idx]
        time_label = self._times[idx].strftime(
            "%H:%M" if self.period_mode == "5H" else "%m/%d %H:%M"
        )

        self._annotation.xy = (idx, price)
        self._annotation.set_text(f"${price:.2f}\n{time_label}")
        self._annotation.set_visible(True)
        self.canvas.draw_idle()

    def _on_leave(self, event):
        self._hide_annotation()

    def _hide_annotation(self):
        if self._annotation is not None and self._annotation.get_visible():
            self._annotation.set_visible(False)
            self.canvas.draw_idle()

    # ---------- theming ----------

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(fg_color=theme["surface"], border_color=theme["border"], border_width=1)
        self._update_toggle_styles()
        self._style_axes()
        if self._closes:
            self._annotation = self._make_annotation()
        self.canvas.draw_idle()
        if self._last_price is not None:
            positive = self._last_change_pct >= 0
            self.header_label.configure(text_color=theme["success"] if positive else theme["danger"])
        else:
            self.header_label.configure(text_color=theme["text_muted"])
