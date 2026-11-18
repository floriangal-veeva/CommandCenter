# Command Center — Build Progress

Spec: see `command_center_spec.md` (originally in Downloads).

## Parts

- [x] **Part 1 — Scaffold & core infra**: folder structure, `storage.py`
  (atomic JSON store), logging redirect, `themes.json`/`themes.py`,
  `fonts.py`, `main.py` skeleton with 3-column Bento grid + header bar
  (clock, refresh, theme dropdown, font dropdowns — all live/wired),
  hotkey placeholder (comment only, no `keyboard` lib). Run with
  `python main.py` to see it (uses `python.exe` for now so you can see
  console errors; switch to `pythonw.exe` once satisfied).
- [x] **Part 2 — Launcher + Mini-CMD** (Vault Login button dropped per
  user request — not being built at all, not even deferred): 2-column
  launcher grid driven by `config.json.launcher_items`, "+ Add" modal
  (with file-browse), launch via `os.startfile` (works for both local
  exe paths and URLs). Mini-CMD: fixed allowlist of 9 diagnostic
  commands (`widgets/mini_cmd.py::ALLOWLIST`) + a safely-scoped `cd`
  (only `..` or an existing immediate subfolder — blocks drive letters,
  slashes, and `..`-embedded traversal), Up/Down history (in-memory
  only, not persisted — only `cwd` goes to `state.json` per spec),
  Clear button, 15s timeout + `CREATE_NO_WINDOW`, runs in a background
  thread and reports back through the shared `event_queue`.
- [x] **Part 3 — Top 3 + Stock chart**: Daily Top 3 (3 checkbox+entry rows,
  checked = overstrike font + dimmed text, debounced save to `state.json`).
  VEEV Stock Chart: `yfinance` + embedded `matplotlib` (`FigureCanvasTkAgg`,
  no pyplot), 5H (`period=5d, interval=5m, tail(60)`) / 5D
  (`period=5d, interval=30m`) toggle, plotted on sequential bar indices,
  themed via `success`/`danger` roles, "Offline / Retrying" fallback on
  fetch failure, wired into the header Refresh button + the 2-hour
  auto-refresh scheduler via `self.refreshable_widgets`. Installed
  `yfinance` + `matplotlib` into the env (weren't present before).
  Live-fetch verified against VEEV during build.
- [x] **Part 4 — News**: 4 tabs (Hungarian/Movies/Tech/Gaming), Hungarian
  default-active, feed URLs + empty `muted_keywords` from `config.json`,
  same raw-bytes-then-`feedparser.parse` + 5s-timeout pattern as the rest
  of the app, headlines clickable (open link via `os.startfile`), wired
  into the refresh cycle. All 4 default feed URLs (telex.hu, Variety,
  The Verge, PCGamer) verified reachable and parseable during build.
  Also consolidated the 3 separate header dropdowns (Theme/UI Font/Mono
  Font) into one "Theme & Font" button that opens a small settings modal.
- [x] **Part 5 — Notes**: integrated page (`widgets/notes/notes_page.py`,
  `NotesPage(ctk.CTkFrame)`) toggled into the main window via the header
  "Notes"/"Dashboard" button — **no longer a separate OS window** (changed
  2026-11-18 per user request; the old `CTkToplevel`-based
  `widgets/notes/notes_window.py` was deleted). `main.py` stacks
  `dashboard_frame` and `notes_page` in the same grid cell inside
  `content_container` and raises whichever is active via `tkraise()`; both
  stay alive and themed permanently (registered once at boot, not on
  open/close). One `.txt` per note in `./notes/` (`widgets/notes/note_store.py`),
  title/filename logic per spec (explicit title → slugified filename +
  label; blank → "Note 1", "Note 2"... renamable later), search bar across
  all filenames+contents, ~600ms debounced autosave (atomic write), flushed
  immediately on note-switch, on toggling back to the dashboard, and on
  app close/quit (`NotesPage.flush_pending_save()`).
- [x] **Part 6 — Tray + auto-refresh wiring + placeholders**: `pystray`
  (newly installed) with Show/Refresh/Quit, tray icon generated with PIL
  (no bundled asset). Clicking X now hides to tray (`root.withdraw()`)
  instead of quitting; real quit is tray-menu-only (`_quit_app`), persists
  window geometry first. Tray callbacks marshal back to the Tk main thread
  via `root.after(0, ...)` since pystray's own loop runs in a background
  thread. Auto-refresh wiring (2-hour scheduler + boot refresh + manual
  button) was already done as part of Parts 1/3. Autostart/hotkey remain
  placeholder-only, untouched, per spec §3.
- [x] **Part 7 — Billable Hours Logger** (`widgets/billable.py`,
  `BillableWidget`, built 2026-11-18). The 3 blanks (picklist, Service
  Resource constant, Vault date format) were never actually supplied by the
  user, so rather than block, these became **self-service config** exposed
  via a gear (⚙) button on the widget that opens a settings modal:
  - **Type**: `CTkOptionMenu` populated from `config.json["billable_categories"]`
    if non-empty, else falls back to a free-text `CTkEntry` so the feature
    works immediately with zero config.
  - **Service Resource**: constant from `config.json["service_resource"]`
    (default `""`), shown read-only under the title; entry logging is
    blocked with an inline error until it's set via the gear modal.
  - **Date Performed**: a Python strftime pattern from
    `config.json["date_performed_format"]` (default `"%Y-%m-%d"` ISO),
    shown as a live-example hint under the date field; "Today" button
    fills it. **User still needs to confirm/correct this against Vault's
    actual loader format** — flagged, not verified against real Vault.
  - On "Log Entry": validates Type/Hours/Service Resource/Date, computes
    the ISO week from the **parsed Date Performed value** (not today —
    per spec), and appends a row to
    `timesheets/billable_<ISO-year>-W<ISO-week>.csv` (creating it with a
    header row `Type,Hours,Service Resource,Date Performed` if new).
    `timesheets/` already existed as an empty folder from last session.

## Post-Part-3 tweaks (done)

- Mini-CMD: allowlist removed entirely — runs whatever's typed via
  `cmd /c <input>` (personal tool, user's own machine, still 15s timeout +
  `CREATE_NO_WINDOW`, cwd still tracked/persisted). `cd` relaxed to accept
  any real directory, not just immediate subfolders.
- Mini-CMD output box height reduced (160 → 90).
- Launcher rewritten as a tiled icon grid (`widgets/icons.py`): real icons
  extracted from .exe/.lnk via `pywin32` (newly installed, added to
  requirements.txt), procedurally-drawn placeholder glyph for URLs/anything
  icon-less. 3 columns, icon-above-label tiles.
- Daily Top 3: tracks `updated_at` per item (only bumped when text actually
  changes). Unchecked + non-empty + 2+ days old → persistent danger-colored
  highlight, plus a reminder popup on every refresh (manual click or the
  2-hour auto-refresh tick) until checked off or edited. Added a boot-time
  `refresh_all()` call (spec said auto-refresh fires "on boot" too — Part 3
  had missed that).
- Stock chart: hover now shows an exact-price tooltip (date/time + $price)
  tracking the mouse across the plotted line.

## Post-Part-4 tweaks (done, 2026-11-18)

- `themes.json`: added 5 more themes (Nord, Dracula, Solarized Dark, Forest,
  Sunset Warm) alongside the original 2 — 7 total, all 10 roles filled.
- "Theme & Font" modal now has a "+ Add Theme" button → opens a picker with
  a native color-chooser swatch per role (seeded from the currently active
  theme), writes to `themes.json` via `ThemeManager.save_theme()` (same
  atomic-write pattern), and applies it immediately.
- News: redesigned as hoverable headline cards (was a plain bullet list) +
  each headline now shows a relative published timestamp ("2h ago", falls
  back to a date after a week) parsed from the feed's `published_parsed`.
- **Judgment call, flagged for visibility**: Launcher icons for URL-type
  items now try to fetch the linked site's own `favicon.ico` directly (not
  a third-party icon API/aggregator) in a background thread — same 5s-
  timeout, offline-safe, never-blocks-UI pattern as everything else, falls
  back to the generated placeholder glyph on failure. This is one extra
  outbound network request per unique link domain (beyond the already-
  present News/Stock network calls). Spec's original design goal was
  "no cloud APIs" on an EDR-monitored fleet laptop — this isn't a cloud
  API/OAuth/paid key, just a direct GET to the linked site itself (same
  domain the user is already linking to), but flagging it since it's a
  judgment call, not an explicit ask. Easy to rip back out to fully-offline
  icons if unwanted — see `widgets/icons.py::fetch_favicon_image` +
  `widgets/launcher.py`'s `_fetch_favicon_worker`.
- Local `.exe`/`.lnk` icon extraction (via `pywin32`) is unchanged/still
  fully offline.

## Post-Part-7 tweaks (done, 2026-11-18)

- **Icon selection** (user: "still not a better version — make sure I can
  select"): `widgets/icons.py::load_custom_icon_image(path, size)` loads
  any Pillow-readable file (.ico/.png/.jpg/...) as a launcher icon. The
  "+ Add" modal now has an optional "Icon" field + Browse (file picker,
  filtered to image types). Existing tiles got a right-click context menu
  (`LauncherWidget._open_item_context_menu`) with "Change Icon...",
  "Clear Custom Icon" (only shown if one's set), and "Remove" — so
  already-added items can get a manual icon too, not just new ones. A
  manually-set `icon_path` always wins over the auto-extracted/favicon
  icon and skips the favicon network fetch entirely for that item.
  The auto favicon-fetch-from-linked-site behavior from the prior session
  is unchanged/still in place as the default for URL items with no
  `icon_path` — still flagged as a judgment call, see prior entry above.

## Post-Part-7 tweaks round 2 (done, 2026-11-18)

- **Layout**: per user request, Notes went back to a permanent dashboard
  card (not a toggled full-window page) — center column is now
  Launcher → Notes (Notes expands to fill). Left column reordered to
  Top 3 → Billable → Mini-CMD (Mini-CMD expands). Right column unchanged
  (Stock Chart → News). Header's "Notes"/"Dashboard" toggle button was
  removed entirely since there's nothing to toggle anymore.
- **Bug fix — launcher item deletion silently did nothing**: the
  right-click context menu's `<Button-3>` binding was only attached to the
  outer `CTkButton`, but clicks land on its internal Canvas/Label children
  which don't forward events upward. Fixed via
  `LauncherWidget._bind_context_menu`, a recursive bind over
  `winfo_children()`. "Remove"/"Change Icon..."/"Clear Custom Icon" (added
  last session) now actually fire.
- **Bug fix — Notes note-list background didn't follow theme switches**:
  `CTkScrollableFrame`'s `fg_color="transparent"` only resolves once at
  construction; without an explicit `.configure(fg_color=...)` call on
  every `apply_theme`, its internal canvas/frame stayed on the color from
  whichever theme was active at startup. `notes_page.py::apply_theme` now
  explicitly reconfigures `note_list_frame`'s `fg_color` every time.
- **Header accent strip**: added a 3px `header_accent` frame between the
  header and the body (`main.py`), colored from `theme["primary"]` and
  updated in `_apply_header_theme`. The header itself uses `theme["surface"]`
  same as the cards, which barely differs from `background` in some themes
  (e.g. Monochrome) — the accent strip makes a theme switch visually obvious
  regardless of which theme it is. Root grid rows shifted (header=0,
  accent=1, body=2) to fit it in.
- **Open-folder buttons**: both `BillableWidget` and `NotesPage` got a
  "\U0001F4C2" button in their header row (`_open_folder`, `os.startfile`
  on `timesheets_dir` / `notes_dir` respectively).

## Post-Part-7 tweaks round 3 (done, 2026-11-18)

- **Native title bar color**: the in-app header accent strip (round 2) was
  the wrong target — user meant the actual OS window title bar (the strip
  with minimize/maximize/close). ctk/tkinter don't theme that; added
  `CommandCenterApp._set_titlebar_colors` (`main.py`), called from
  `_apply_header_theme` on every theme switch/boot. Uses `ctypes` +
  `dwmapi.DwmSetWindowAttribute` with `DWMWA_CAPTION_COLOR` (35) /
  `DWMWA_TEXT_COLOR` (36) against the HWND from
  `GetParent(root.winfo_id())` — standard trick for Tkinter on Windows.
  **Requires Windows 11 build 22000+**; wrapped in try/except, logs and
  no-ops otherwise (same best-effort pattern as tray/favicon/etc.). Colors
  it with `theme["surface"]` / `theme["text"]`, matching the in-app header.
- **Text contrast fix**: several buttons either hardcoded
  `text_color=theme["background"]` (assuming background is always dark —
  breaks for bright custom themes made via "+ Add Theme", or whenever the
  accent itself is already light) or never set `text_color` at all
  (defaulting to CTk's own default, which is unreadable against a bright
  accent like Monochrome's white `primary`). Added
  `themes.py::contrasting_text_color(hex)` — luminance-based black/white
  pick against the *actual* fg_color of that element, not an assumed role.
  Applied everywhere an accent role (`primary`/`tertiary`) is used as a
  button's `fg_color` or a checkbox's `fg_color` (checkmark): header's
  Refresh/Theme & Font buttons and the "+ Add Theme" button (`main.py`),
  Mini-CMD's Run/Clear (`mini_cmd.py`), Billable's gear/Today/folder/Log
  Entry buttons + Type dropdown (`billable.py`), Launcher's "+ Add"
  (`launcher.py`), Notes' "+ New"/folder buttons (`notes_page.py`), and Top
  3's checkbox checkmark (`top3.py`).

## Post-Part-7 tweaks round 4 (done, 2026-11-18)

- **Bug fix — deleting a note file directly (via the folder button) didn't
  update the list on Refresh**: `NotesPage` was never added to
  `main.py`'s `refreshable_widgets`, so the header Refresh button (and the
  2-hour auto-refresh) never touched it at all. Added `NotesPage.refresh()`
  and registered it. It re-reads the directory listing, and if the
  currently-open note's file is gone, cancels any pending autosave for it
  first (otherwise the debounced autosave would silently recreate the
  deleted file) before switching to another note / creating a fresh one.
- **In-app delete**: right-click a note in the list → "Delete" (uses the
  already-existing but previously-unwired `note_store.delete_note`), so
  deleting doesn't require going to Explorer at all anymore. Same
  recursive-bind fix as the Launcher's right-click menu (CTkButton's
  internal Canvas/Label children don't forward `<Button-3>` to the outer
  widget).

## Post-Part-7 tweaks round 5 (done, 2026-11-18)

- **Searchable icon library picker**: user dropped the full Lucide icon
  set (2091 `.svg` + matching `.json` tag sidecars) into
  `command_center/icons/`. Added `widgets/icons.py::list_bundled_icons`/
  `search_bundled_icons` (indexes filename + the json's `tags`+`categories`
  once, cached) and a "Pick from Icon Library..." button — in the
  "+ Add Launcher Item" modal and as a new right-click option on existing
  tiles — opening a searchable grid (`LauncherWidget._open_icon_picker`),
  debounced 250ms, capped at 48 results per search.
  **BLOCKED — needs your go-ahead**: Pillow cannot open `.svg` directly
  (confirmed — `Image.open()` raises `UnidentifiedImageError`). Rendering
  needs `svglib` + `reportlab` (pip-installable, pure-Python-ish, no
  native Cairo/GTK runtime needed — deliberately not `cairosvg`, which
  does need that on Windows). My attempt to `pip install` them was
  **denied by the harness's permission classifier** this session (not a
  judgment call on my end — it refused the Bash call outright). Until
  installed: `widgets/icons.py::render_svg_icon` returns `None` and
  `_SVG_WARNED` logs a one-time hint, so the picker still works but tiles
  show as text-only (no thumbnail) and a chosen SVG won't render on the
  launcher tile either (falls back to the placeholder glyph) — nothing
  crashes, it just degrades. **Next step**: user runs
  `pip install svglib reportlab` themselves (or grants Bash permission so
  I can), then SVG icons should render with no further code changes needed
  — `load_custom_icon_image` already dispatches `.svg` through
  `render_svg_icon` (recolors `currentColor` to the neutral glyph grey
  `#8A96A3` before rasterizing, since Lucide icons are stroke-only).
- **Top 3 completion history**: checking a Top 3 item off now appends a
  line to a single running log file, `top3_history.txt` (project root,
  `TOP3_HISTORY_PATH` in `main.py`) — format `"<task text> - <YYYY-MM-DD>"`,
  one line per completion, never rotated/truncated. Only fires on the
  unchecked→checked transition (not on uncheck), via
  `Top3Widget._on_toggle`/`_append_history`. Plain text, append-only, easy
  to open directly if wanted — "any format" was the ask.

## Notes for next session

- Project root: `C:\Users\Flórián Gál\command_center`
- Dependencies: `pip install -r requirements.txt` (customtkinter already
  confirmed installed in the Python 3.14 env used to build this).
- All 7 parts are now built — no more placeholder cards in the Bento grid.
- `config.json["billable_categories"]` is still `[]` by default (free-text
  Type field until filled); `service_resource` and `date_performed_format`
  are user-editable via the Billable widget's gear (⚙) settings modal, not
  hardcoded — see Part 7 above. Vault's exact loader date format was never
  confirmed by the user; double-check before relying on real submissions.
