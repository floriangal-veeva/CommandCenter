"""News — 4 fixed topic tabs (Hungarian default-active), feed URLs and mute
keywords read from config.json. Same raw-bytes-then-parse, 5s-timeout
network pattern as the rest of the app (feedparser has no native timeout).
Headlines render as hoverable cards with a relative published timestamp."""

import calendar
import datetime
import os
import threading
import urllib.request

import customtkinter as ctk
import feedparser

TOPICS = ["Hungarian", "Movies", "Tech", "Gaming"]
FETCH_TIMEOUT_SECONDS = 5.0
MAX_HEADLINES = 14


def _format_pub_time(entry):
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not struct:
        return ""
    try:
        dt = datetime.datetime.fromtimestamp(calendar.timegm(struct))
    except (OverflowError, OSError, ValueError):
        return ""

    delta = datetime.datetime.now() - dt
    seconds = delta.total_seconds()
    if seconds < 0:
        return dt.strftime("%H:%M")
    minutes = seconds / 60
    if minutes < 60:
        return f"{max(1, int(minutes))}m ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    days = hours / 24
    if days < 7:
        return f"{int(days)}d ago"
    return dt.strftime("%Y-%m-%d")


class NewsWidget(ctk.CTkFrame):
    def __init__(self, master, event_queue, config_store, config, ui_font="Segoe UI"):
        super().__init__(master, corner_radius=8)
        self.event_queue = event_queue
        self.config_store = config_store
        self.config = config
        self.ui_font = ui_font
        self.active_topic = TOPICS[0]
        self._headlines_by_topic = {t: [] for t in TOPICS}
        self._theme = {}
        self._card_frames = []

        self.title_label = ctk.CTkLabel(self, text="News", anchor="w", font=(self.ui_font, 13, "bold"))
        self.title_label.pack(fill="x", padx=12, pady=(10, 6))

        tab_row = ctk.CTkFrame(self, fg_color="transparent")
        tab_row.pack(fill="x", padx=12)
        self.tab_buttons = {}
        for topic in TOPICS:
            btn = ctk.CTkButton(
                tab_row, text=topic, width=1, height=28, corner_radius=6, font=(self.ui_font, 11),
                command=lambda t=topic: self._select_topic(t),
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.tab_buttons[topic] = btn

        self.status_label = ctk.CTkLabel(self, text="", anchor="w", font=(self.ui_font, 10))
        self.status_label.pack(fill="x", padx=12, pady=(6, 0))

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", height=240)
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self._update_tab_styles()
        self.refresh()

    # ---------- tabs ----------

    def _select_topic(self, topic):
        if topic == self.active_topic:
            return
        self.active_topic = topic
        self._update_tab_styles()
        self._render_headlines()
        if not self._headlines_by_topic.get(topic):
            self._fetch_topic(topic)

    # ---------- fetch (background thread, per spec §2) ----------

    def refresh(self):
        self.status_label.configure(text="Refreshing...")
        for topic in TOPICS:
            self._fetch_topic(topic)

    def _fetch_topic(self, topic):
        urls = self.config.get("news_feeds", {}).get(topic, [])
        threading.Thread(target=self._fetch_worker, args=(topic, urls), daemon=True).start()

    def _fetch_worker(self, topic, urls):
        headlines = []
        ok = False
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                raw = urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS).read()
                parsed = feedparser.parse(raw)
                for entry in parsed.entries:
                    headlines.append(
                        {
                            "title": entry.get("title", "(no title)"),
                            "link": entry.get("link", ""),
                            "published": _format_pub_time(entry),
                        }
                    )
                ok = True
            except Exception as e:
                print(f"[news] fetch failed for {topic} ({url}): {e}")
        self.event_queue.put(lambda: self._on_fetch_done(topic, headlines, ok))

    def _on_fetch_done(self, topic, headlines, ok):
        if ok:
            self._headlines_by_topic[topic] = headlines
        elif not self._headlines_by_topic.get(topic):
            self._headlines_by_topic[topic] = None  # None = offline marker
        if topic == self.active_topic:
            self._render_headlines()
        self.status_label.configure(text=f"Updated {datetime.datetime.now().strftime('%H:%M')}")

    # ---------- render ----------

    def _render_headlines(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._card_frames = []

        headlines = self._headlines_by_topic.get(self.active_topic)
        if headlines is None:
            ctk.CTkLabel(
                self.list_frame, text="Offline / Retrying", text_color=self._theme.get("danger", "#F87171")
            ).pack(anchor="w", pady=4, padx=4)
            return
        if not headlines:
            ctk.CTkLabel(
                self.list_frame, text="Loading...", text_color=self._theme.get("text_muted", "#999999")
            ).pack(anchor="w", pady=4, padx=4)
            return

        muted = [kw.lower() for kw in self.config.get("muted_keywords", []) if kw]
        shown = 0
        for item in headlines:
            title = item["title"]
            if any(kw in title.lower() for kw in muted):
                continue
            self._add_card(item)
            shown += 1
            if shown >= MAX_HEADLINES:
                break

        if shown == 0:
            ctk.CTkLabel(
                self.list_frame, text="(all headlines muted)", text_color=self._theme.get("text_muted", "#999999")
            ).pack(anchor="w", pady=4, padx=4)

    def _add_card(self, item):
        base_color = self._theme.get("background", "#000000")
        hover_color = self._theme.get("border", "#333333")

        card = ctk.CTkFrame(self.list_frame, fg_color=base_color, corner_radius=6)
        card.pack(fill="x", pady=3, padx=2)

        title_label = ctk.CTkLabel(
            card,
            text=item["title"],
            anchor="w",
            justify="left",
            wraplength=250,
            font=(self.ui_font, 12),
            text_color=self._theme.get("text", "#FFFFFF"),
            cursor="hand2",
        )
        title_label.pack(fill="x", padx=10, pady=(8, 0), anchor="w")

        meta_label = ctk.CTkLabel(
            card,
            text=item["published"] or "",
            anchor="w",
            font=(self.ui_font, 9),
            text_color=self._theme.get("text_muted", "#999999"),
            cursor="hand2",
        )
        meta_label.pack(fill="x", padx=10, pady=(1, 8), anchor="w")

        widgets = (card, title_label, meta_label)

        def on_enter(_e):
            card.configure(fg_color=hover_color)

        def on_leave(_e):
            card.configure(fg_color=base_color)

        link = item["link"]
        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            if link:
                w.bind("<Button-1>", lambda e, l=link: self._open_link(l))

        self._card_frames.append({"card": card, "base": base_color, "hover": hover_color})

    def _open_link(self, link):
        try:
            os.startfile(link)
        except OSError as e:
            print(f"[news] failed to open {link!r}: {e}")

    # ---------- theming ----------

    def _update_tab_styles(self):
        active = self._theme.get("primary", "#38BDF8")
        inactive = self._theme.get("tertiary", "#777777")
        for topic, btn in self.tab_buttons.items():
            btn.configure(fg_color=active if topic == self.active_topic else inactive)

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(fg_color=theme["surface"], border_color=theme["border"], border_width=1)
        self.title_label.configure(text_color=theme["text"])
        self.status_label.configure(text_color=theme["text_muted"])
        self._update_tab_styles()
        self._render_headlines()

    def apply_ui_font(self, family):
        self.ui_font = family
        self.title_label.configure(font=(family, 13, "bold"))
        for btn in self.tab_buttons.values():
            btn.configure(font=(family, 11))
        self._render_headlines()
