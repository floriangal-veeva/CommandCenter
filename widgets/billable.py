"""Billable Hours Logger — Part 7. Appends rows to a per-ISO-week CSV
(timesheets/billable_<ISO-year>-W<ISO-week>.csv) where the week is driven by
the Date Performed value entered, not today's date. Columns, in order:
Type, Hours, Service Resource, Date Performed.

Three inputs are user-owned and self-service via the gear/settings modal
rather than hardcoded, since only the user knows them:
  - billable_categories (Type picklist) — config.json
  - service_resource (constant value repeated on every row) — config.json
  - date_performed_format (strftime pattern Vault's loader expects,
    default ISO "%Y-%m-%d") — config.json
"""

import csv
import datetime
import os

import customtkinter as ctk

from themes import contrasting_text_color

DEFAULT_DATE_FORMAT = "%Y-%m-%d"


class BillableWidget(ctk.CTkFrame):
    def __init__(self, master, config_store, config, timesheets_dir, ui_font="Segoe UI"):
        super().__init__(master, corner_radius=8)
        self.config_store = config_store
        self.config = config
        self.timesheets_dir = timesheets_dir
        self.ui_font = ui_font
        self._theme = {}
        os.makedirs(self.timesheets_dir, exist_ok=True)

        header_row = ctk.CTkFrame(self, fg_color="transparent")
        header_row.pack(fill="x", padx=12, pady=(10, 6))
        self.title_label = ctk.CTkLabel(
            header_row, text="Billable Hours Logger", anchor="w", font=(self.ui_font, 13, "bold")
        )
        self.title_label.pack(side="left")
        self.settings_button = ctk.CTkButton(
            header_row, text="⚙", width=28, command=self._open_settings_modal
        )
        self.settings_button.pack(side="right")
        self.folder_button = ctk.CTkButton(
            header_row, text="\U0001F4C2", width=28, command=self._open_folder
        )
        self.folder_button.pack(side="right", padx=(0, 6))

        self.resource_label = ctk.CTkLabel(self, text="", anchor="w", font=(self.ui_font, 10))
        self.resource_label.pack(fill="x", padx=12, pady=(0, 4))

        type_row = ctk.CTkFrame(self, fg_color="transparent")
        type_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(type_row, text="Type", width=70, anchor="w", font=(self.ui_font, 11)).pack(side="left")
        self.type_widget = None
        self._build_type_widget(type_row)

        hours_row = ctk.CTkFrame(self, fg_color="transparent")
        hours_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(hours_row, text="Hours", width=70, anchor="w", font=(self.ui_font, 11)).pack(side="left")
        self.hours_entry = ctk.CTkEntry(hours_row, font=(self.ui_font, 12))
        self.hours_entry.pack(side="left", fill="x", expand=True)

        date_row = ctk.CTkFrame(self, fg_color="transparent")
        date_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(date_row, text="Date", width=70, anchor="w", font=(self.ui_font, 11)).pack(side="left")
        self.date_entry = ctk.CTkEntry(date_row, font=(self.ui_font, 12))
        self.date_entry.pack(side="left", fill="x", expand=True)
        self.today_button = ctk.CTkButton(date_row, text="Today", width=50, command=self._fill_today)
        self.today_button.pack(side="left", padx=(6, 0))

        self.format_hint_label = ctk.CTkLabel(self, text="", anchor="w", font=(self.ui_font, 9))
        self.format_hint_label.pack(fill="x", padx=12, pady=(0, 6))

        self.log_button = ctk.CTkButton(self, text="Log Entry", command=self._log_entry)
        self.log_button.pack(padx=12, pady=(0, 6), anchor="e")

        self.status_label = ctk.CTkLabel(self, text="", anchor="w", font=(self.ui_font, 10))
        self.status_label.pack(fill="x", padx=12, pady=(0, 10))

        self._refresh_hint_and_resource()
        self._fill_today()

    # ---------- dynamic Type field: dropdown if a picklist is configured, else free text ----------

    def _build_type_widget(self, parent):
        categories = self.config.get("billable_categories") or []
        if self.type_widget is not None:
            self.type_widget.destroy()
        if categories:
            self.type_widget = ctk.CTkOptionMenu(parent, values=categories)
            self.type_widget.set(categories[0])
        else:
            self.type_widget = ctk.CTkEntry(
                parent, font=(self.ui_font, 12), placeholder_text="No picklist configured — type freely"
            )
        self.type_widget.pack(side="left", fill="x", expand=True)
        if self._theme:
            self._style_type_widget()

    def _get_type_value(self):
        if isinstance(self.type_widget, ctk.CTkOptionMenu):
            return self.type_widget.get()
        return self.type_widget.get().strip()

    def _fill_today(self):
        fmt = self.config.get("date_performed_format", DEFAULT_DATE_FORMAT)
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, datetime.date.today().strftime(fmt))

    def _refresh_hint_and_resource(self):
        fmt = self.config.get("date_performed_format", DEFAULT_DATE_FORMAT)
        example = datetime.date.today().strftime(fmt)
        self.format_hint_label.configure(text=f"Date format: {fmt}  (e.g. {example})")
        resource = self.config.get("service_resource", "").strip()
        if resource:
            self.resource_label.configure(text=f"Service Resource: {resource}")
        else:
            self.resource_label.configure(text="Service Resource: (not set — click ⚙ to set it)")

    # ---------- logging ----------

    def _log_entry(self):
        type_value = self._get_type_value()
        hours_raw = self.hours_entry.get().strip()
        date_raw = self.date_entry.get().strip()
        resource = self.config.get("service_resource", "").strip()
        fmt = self.config.get("date_performed_format", DEFAULT_DATE_FORMAT)

        if not type_value:
            self._set_status("Type is required.", error=True)
            return
        try:
            hours = float(hours_raw)
        except ValueError:
            self._set_status("Hours must be a number.", error=True)
            return
        if not resource:
            self._set_status("Set a Service Resource first (⚙).", error=True)
            return
        try:
            parsed_date = datetime.datetime.strptime(date_raw, fmt).date()
        except ValueError:
            self._set_status(f"Date must match format {fmt}.", error=True)
            return

        iso_year, iso_week, _ = parsed_date.isocalendar()
        filename = f"billable_{iso_year}-W{iso_week:02d}.csv"
        path = os.path.join(self.timesheets_dir, filename)
        is_new = not os.path.exists(path)

        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["Type", "Hours", "Service Resource", "Date Performed"])
            writer.writerow([type_value, hours, resource, parsed_date.strftime(fmt)])

        self.hours_entry.delete(0, "end")
        self._set_status(f"Logged to {filename}", error=False)

    def _open_folder(self):
        try:
            os.startfile(self.timesheets_dir)
        except OSError as e:
            print(f"[billable] failed to open folder: {e}")

    def _set_status(self, text, error):
        color = self._theme.get("danger" if error else "success", "#F87171" if error else "#4ADE80")
        self.status_label.configure(text=text, text_color=color)

    # ---------- settings modal (self-service for the 3 user-owned inputs) ----------

    def _open_settings_modal(self):
        theme = self._theme or {}
        modal = ctk.CTkToplevel(self)
        modal.title("Billable Hours Settings")
        modal.geometry("360x420")
        modal.grab_set()
        modal.configure(fg_color=theme.get("surface", "#1a1a1a"))

        def label(text):
            ctk.CTkLabel(modal, text=text, anchor="w", text_color=theme.get("text", "#FFFFFF")).pack(
                fill="x", padx=16, pady=(14, 2)
            )

        label("Service Resource (constant, written on every row)")
        resource_entry = ctk.CTkEntry(modal)
        resource_entry.insert(0, self.config.get("service_resource", ""))
        resource_entry.pack(fill="x", padx=16)

        label("Date Performed format (Python strftime pattern — must match\nVault's loader, e.g. %Y-%m-%d or %d-%b-%Y)")
        format_entry = ctk.CTkEntry(modal)
        format_entry.insert(0, self.config.get("date_performed_format", DEFAULT_DATE_FORMAT))
        format_entry.pack(fill="x", padx=16)

        label("Type picklist (one value per line — leave empty for free text)")
        categories_box = ctk.CTkTextbox(modal, height=160)
        categories_box.insert("1.0", "\n".join(self.config.get("billable_categories") or []))
        categories_box.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        def save():
            self.config["service_resource"] = resource_entry.get().strip()
            fmt = format_entry.get().strip() or DEFAULT_DATE_FORMAT
            self.config["date_performed_format"] = fmt
            raw_categories = categories_box.get("1.0", "end-1c")
            categories = [line.strip() for line in raw_categories.splitlines() if line.strip()]
            self.config["billable_categories"] = categories
            self.config_store.write(self.config)

            type_row_parent = self.type_widget.master
            self._build_type_widget(type_row_parent)
            self._refresh_hint_and_resource()
            self._fill_today()
            modal.destroy()

        ctk.CTkButton(modal, text="Save", command=save).pack(pady=10)

    # ---------- theming / fonts ----------

    def _style_type_widget(self):
        theme = self._theme
        if isinstance(self.type_widget, ctk.CTkOptionMenu):
            self.type_widget.configure(
                fg_color=theme["background"], button_color=theme["tertiary"],
                button_hover_color=theme["secondary"], text_color=theme["text"],
            )
        else:
            self.type_widget.configure(fg_color=theme["background"], border_color=theme["border"], text_color=theme["text"])

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(fg_color=theme["surface"], border_color=theme["border"], border_width=1)
        self.title_label.configure(text_color=theme["text"])
        self.resource_label.configure(text_color=theme["text_muted"])
        self.format_hint_label.configure(text_color=theme["text_muted"])
        self._style_type_widget()
        self.hours_entry.configure(fg_color=theme["background"], border_color=theme["border"], text_color=theme["text"])
        self.date_entry.configure(fg_color=theme["background"], border_color=theme["border"], text_color=theme["text"])
        for btn in (self.settings_button, self.today_button, self.folder_button):
            btn.configure(
                fg_color=theme["tertiary"], hover_color=theme["secondary"],
                text_color=contrasting_text_color(theme["tertiary"]),
            )
        self.log_button.configure(
            fg_color=theme["primary"], hover_color=theme["secondary"],
            text_color=contrasting_text_color(theme["primary"]),
        )
        self.status_label.configure(text_color=theme["text_muted"])

    def apply_ui_font(self, family):
        self.ui_font = family
        self.title_label.configure(font=(family, 13, "bold"))
        self.hours_entry.configure(font=(family, 12))
        self.date_entry.configure(font=(family, 12))
        if not isinstance(self.type_widget, ctk.CTkOptionMenu):
            self.type_widget.configure(font=(family, 12))
