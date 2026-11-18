# Command Center

A fully local, offline Windows desktop productivity dashboard. No cloud APIs, no OAuth, no subscriptions — everything runs and saves locally.

## What it does

- **App & Link Launcher** — quick-access buttons to your tools/sites, editable from the UI
- **Mini-CMD** — fixed allowlist of read-only diagnostic commands (`git status`, `ipconfig`, etc.), with history and persistent working directory
- **Vault Login** — one button opens a plain `cmd.exe` window for `vault login` (SSO), fully separate from Mini-CMD, nothing from this flow is ever logged
- **Daily Top 3** — three persistent tasks with checkboxes
- **Billable Hours Logger** — logs hours to a weekly CSV (ISO week rotation), shows live week total
- **Notes** — searchable, multi-note board; one plain `.txt` file per note in `./notes/`, openable in any text editor
- **VEEV Stock Chart** — live price via `yfinance`, 5H/5D toggle
- **News** — 4 feeds (Hungarian/Telex default, Movies, Tech, Gaming), with a keyword mute list
- **System tray** — closing the window minimizes to tray instead of quitting

## Requirements

- Windows, Python 3.x
- Installed packages:
  ```
  pip install customtkinter yfinance matplotlib feedparser pystray pillow
  ```

## Running it

```
pythonw.exe main.py
```

Runs headless (no console window). Logs go to `./logs/app.log`.

No autostart is configured — launch manually (e.g. a desktop shortcut) until auto-start-at-login is explicitly enabled later.

## Project structure

```
main.py              # App init, Bento grid, tray icon, refresh scheduler
themes.py             # Loads themes.json, applies theme + font to all widgets
themes.json           # Theme definitions (colors) — add a theme by adding a JSON block, no code change
fonts.py              # Enumerates installed system fonts
storage.py            # Thread-safe atomic JSON read/write
config.json           # Static settings: launcher items, categories, news feed URLs, mute keywords, font/theme choice
state.json             # Volatile state: Top-3, window position, Mini-CMD working directory
widgets/
  launcher.py
  mini_cmd.py
  vault_login.py
  top3.py
  timesheet.py
  stock_chart.py
  news.py
  notes/
    notes_window.py
    note_store.py
notes/                # Your note .txt files live here
timesheets/            # billable_<ISO-week>.csv files
logs/
  app.log
```

## Customizing

- **Themes** — edit `themes.json`; the theme dropdown picks up new entries automatically. Each theme needs: `background`, `surface`, `border`, `text`, `text_muted`, `primary`, `secondary`, `tertiary`, `success`, `danger`.
- **Fonts** — pulled from fonts already installed on your machine; no setup needed.
- **News feeds / mute keywords** — edit the relevant arrays in `config.json`.
- **Launcher items / timesheet categories** — editable via the "+ Add" button in-app, or directly in `config.json`.

## Not included (by design, for now)

- Voice dictation — deferred, revisit later
- Auto-start at login — placeholder only, pending IT sign-off on a fleet-managed machine
- Global hotkey — placeholder only, same reason
- Open/arbitrary shell access — Mini-CMD is intentionally a fixed command allowlist, not a general terminal

See `command_center_spec.md` for the full build spec and the reasoning behind these calls.

<img width="959" height="515" alt="image" src="https://github.com/user-attachments/assets/09448c2c-ff96-48ce-bbd9-78306e11dee0" />

