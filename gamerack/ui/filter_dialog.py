"""The filter dialog — a modal window inside the app, not a dropdown.

Sources, sorting, the backlog threshold and hidden games live here, where
there is room to label them and to say how many games survive the choice. Only
the two settings that get toggled constantly stay in the view menu: the view
mode and "installed only".
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk  # noqa: E402

# Everything the dialog owns, with the value that counts as "not filtering".
# Used both for the reset button and to tell whether a filter is in effect.
NEUTRAL = {
    "show_hidden": False,
    "backlog_only": False,
    "filter_sources": True,
}


class FilterDialog(Adw.Dialog):
    """Presented over the window; every change applies at once."""

    __gtype_name__ = "GamerackFilterDialog"

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, settings, buckets, sorts, counter):
        super().__init__(title="Filter", content_width=480,
                         content_height=700)
        self.settings = settings
        self.buckets = buckets
        self.sorts = sorts
        # Called to ask how many games the current choice leaves; the dialog
        # itself knows nothing about the library.
        self.counter = counter
        self._loading = False

        self.reset_button = Gtk.Button(label="Zurücksetzen")
        self.reset_button.add_css_class("flat")
        self.reset_button.connect("clicked", lambda *_: self._reset())

        header = Adw.HeaderBar()
        header.pack_start(self.reset_button)

        self.summary = Gtk.Label(xalign=0.5, wrap=True)
        self.summary.add_css_class("stats-note")

        page = Adw.PreferencesPage()
        page.add(self._sort_group())
        page.add(self._source_group())
        page.add(self._backlog_group())
        page.add(self._extra_group())

        # The count goes in the bottom bar, not into the content: an
        # AdwPreferencesPage scrolls on its own, and a second scroller around
        # it would let the one number you want to watch slide out of sight.
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        footer.set_margin_top(10)
        footer.set_margin_bottom(10)
        footer.append(self.summary)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(page)
        toolbar.add_bottom_bar(footer)
        self.set_child(toolbar)

        self._load()

    # --- groups -------------------------------------------------------------

    def _sort_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Sortieren nach")
        self.sort_keys = list(self.sorts)
        model = Gtk.StringList()
        for key in self.sort_keys:
            model.append(self.sorts[key])
        self.sort_row = Adw.ComboRow(title="Reihenfolge", model=model)
        self.sort_row.connect("notify::selected", self._on_sort)
        group.add(self.sort_row)
        return group

    def _source_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Quellen",
            description="Aus welchen Launchern Spiele gezeigt werden.",
        )
        self.source_rows: dict[str, Adw.SwitchRow] = {}
        for bucket, label in self.buckets:
            row = Adw.SwitchRow(title=label)
            row.connect("notify::active", self._on_source, bucket)
            group.add(row)
            self.source_rows[bucket] = row
        return group

    def _backlog_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Backlog",
            description="Lange ungespielt hebt den Wert, gespielte Stunden "
                        "senken ihn.",
        )
        self.backlog_row = Adw.SwitchRow(title="Nur Backlog zeigen")
        self.backlog_row.connect("notify::active", self._on_backlog)
        group.add(self.backlog_row)

        self.threshold_row = Adw.SpinRow.new_with_range(0, 100, 5)
        self.threshold_row.set_title("Mindestwert")
        self.threshold_row.set_subtitle("60 = installiert und nie gestartet")
        self.threshold_row.connect("notify::value", self._on_threshold)
        group.add(self.threshold_row)
        return group

    def _extra_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Weiteres")
        self.hidden_row = Adw.SwitchRow(
            title="Ausgeblendete zeigen",
            subtitle="Spiele, die du selbst ausgeblendet hast",
        )
        self.hidden_row.connect("notify::active", self._on_hidden)
        group.add(self.hidden_row)
        return group

    # --- state --------------------------------------------------------------

    def _load(self) -> None:
        """Fill the rows from the settings without echoing back a change."""
        self._loading = True
        sort = self.settings["sort"]
        if sort in self.sort_keys:
            self.sort_row.set_selected(self.sort_keys.index(sort))
        for bucket, row in self.source_rows.items():
            row.set_active(self.settings.bucket_shown(bucket))
        self.backlog_row.set_active(self.settings["backlog_only"])
        self.threshold_row.set_value(self.settings["backlog_min"])
        self.hidden_row.set_active(self.settings["show_hidden"])
        self._loading = False
        self._update_summary()

    def _changed(self) -> None:
        if self._loading:
            return
        self.emit("changed")
        self._update_summary()

    def _on_sort(self, row, _param) -> None:
        if self._loading:
            return
        self.settings["sort"] = self.sort_keys[row.get_selected()]
        self._changed()

    def _on_source(self, row, _param, bucket: str) -> None:
        if self._loading:
            return
        self.settings.set_bucket(bucket, row.get_active())
        self._changed()

    def _on_backlog(self, row, _param) -> None:
        if self._loading:
            return
        self.settings["backlog_only"] = row.get_active()
        self.threshold_row.set_sensitive(row.get_active())
        self._changed()

    def _on_threshold(self, row, _param) -> None:
        if self._loading:
            return
        self.settings["backlog_min"] = int(row.get_value())
        self._changed()

    def _on_hidden(self, row, _param) -> None:
        if self._loading:
            return
        self.settings["show_hidden"] = row.get_active()
        self._changed()

    def _reset(self) -> None:
        for bucket, _label in self.buckets:
            self.settings.set_bucket(bucket, NEUTRAL["filter_sources"])
        self.settings["show_hidden"] = NEUTRAL["show_hidden"]
        self.settings["backlog_only"] = NEUTRAL["backlog_only"]
        self._load()
        self.emit("changed")
        self._update_summary()

    def _update_summary(self) -> None:
        shown, total = self.counter()
        self.threshold_row.set_sensitive(self.backlog_row.get_active())
        self.reset_button.set_sensitive(filters_active(self.settings, self.buckets))
        self.summary.set_label(
            f"{shown} von {total} Spielen werden gezeigt"
            if shown != total else f"Alle {total} Spiele werden gezeigt"
        )


def filters_active(settings, buckets) -> bool:
    """True when the dialog's settings hide anything — for the header button."""
    if settings["show_hidden"] != NEUTRAL["show_hidden"]:
        return True
    if settings["backlog_only"] != NEUTRAL["backlog_only"]:
        return True
    return any(not settings.bucket_shown(bucket) for bucket, _label in buckets)
