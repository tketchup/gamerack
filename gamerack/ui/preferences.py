"""Preferences: which sources to scan, and how covers are fetched."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, GObject, Gtk  # noqa: E402

from ..sources import heroic, lutris, steam

SOURCE_ROWS = [
    ("steam", "Steam", "Installierte Spiele und Nicht-Steam-Verknüpfungen"),
    ("heroic", "Heroic", "Epic Games, GOG, Amazon und Sideloads"),
    ("lutris", "Lutris", "Aus der Lutris-Datenbank"),
    ("flatpak", "Flatpak", "Flatpaks mit Kategorie „Spiel“"),
    ("desktop", "Anwendungsmenü", ".desktop-Einträge mit Kategorie „Spiel“"),
]


def _detected() -> dict[str, str]:
    """Tell the user what we actually found, so an empty list is explainable."""
    found = {}
    root = steam.steam_root()
    found["steam"] = str(root) if root else "nicht gefunden"
    root = heroic.heroic_root()
    found["heroic"] = str(root) if root else "nicht gefunden"
    root = lutris.lutris_root()
    found["lutris"] = str(root) if root else "nicht gefunden"
    return found


class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "GamerackPreferences"

    __gsignals__ = {
        "rescan-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "covers-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, settings, pads=None):
        super().__init__()
        self.settings = settings
        self.pads = pads
        self.set_title("Einstellungen")
        self.add(self._sources_page())
        self.add(self._artwork_page())
        self._pad_timer = GLib.timeout_add(400, self._refresh_pads)
        self.connect("closed", lambda *_: GLib.source_remove(self._pad_timer))

    # --- pages --------------------------------------------------------------

    def _sources_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Quellen", icon_name="folder-symbolic")
        detected = _detected()

        group = Adw.PreferencesGroup(
            title="Wo nach Spielen gesucht wird",
            description="Gamerack liest die Launcher nur — es verändert nichts an ihnen.",
        )
        for key, title, subtitle in SOURCE_ROWS:
            if key in detected:
                subtitle = f"{subtitle}\n{detected[key]}"
            row = Adw.SwitchRow(title=title, subtitle=subtitle,
                                active=self.settings.source_enabled(key))
            row.connect("notify::active", self._on_source_toggled, key)
            group.add(row)
        page.add(group)

        filters = Adw.PreferencesGroup(title="Filter")
        scan_all = Adw.SwitchRow(
            title="Alle Anwendungen einbeziehen",
            subtitle="Nicht nur Einträge, die als Spiel gekennzeichnet sind",
            active=self.settings["desktop_scan_all"],
        )
        scan_all.connect("notify::active",
                         lambda row, *_: self._set("desktop_scan_all", row.get_active()))
        filters.add(scan_all)

        hide_launchers = Adw.SwitchRow(
            title="Launcher ausblenden",
            subtitle="Steam, Heroic, Lutris und Bottles nicht als Spiel listen",
            active=self.settings["hide_launchers"],
        )
        hide_launchers.connect(
            "notify::active",
            lambda row, *_: self._set("hide_launchers", row.get_active()),
        )
        filters.add(hide_launchers)

        scan_on_start = Adw.SwitchRow(
            title="Beim Start suchen",
            active=self.settings["scan_on_start"],
        )
        scan_on_start.connect("notify::active",
                              lambda row, *_: self._set("scan_on_start", row.get_active()))
        filters.add(scan_on_start)
        page.add(filters)

        control = Adw.PreferencesGroup(
            title="Bedienung",
            description="Der Konsolenmodus zeigt das Schaufenster im Vollbild. "
                        "Wirkt nach einem Neustart von Gamerack.",
        )
        gamepad = Adw.SwitchRow(
            title="Controller verwenden",
            subtitle="Die Start-Taste öffnet den Konsolenmodus, sobald das "
                     "Fenster im Vordergrund ist",
            active=self.settings["gamepad"],
        )
        gamepad.connect("notify::active",
                        lambda row, *_: self._set("gamepad", row.get_active()))
        control.add(gamepad)

        ambient = Adw.SwitchRow(
            title="Ambient-Modus",
            subtitle="Im Schaufenster nach einer Weile ohne Eingabe "
                     "Screenshots im Vollbild zeigen",
            active=self.settings["ambient"],
        )
        ambient.connect("notify::active",
                        lambda row, *_: self._set("ambient", row.get_active()))
        control.add(ambient)

        delay = Adw.SpinRow.new_with_range(15, 600, 15)
        delay.set_title("Wartezeit")
        delay.set_subtitle("Sekunden Stillstand, bis er startet")
        delay.set_value(self.settings["ambient_delay"])
        delay.connect("notify::value",
                      lambda row, *_: self._set("ambient_delay",
                                                int(row.get_value())))
        control.add(delay)

        # Live, because a controller that does nothing gives no other clue as to
        # whether Gamerack sees it, sees it but misreads it, or never got it.
        self.pad_row = Adw.ActionRow(title="Erkannte Controller")
        self.pad_row.add_css_class("property")
        control.add(self.pad_row)

        self.pad_input_row = Adw.ActionRow(
            title="Zuletzt empfangen",
            subtitle="Drücke eine Taste, um die Verbindung zu prüfen",
        )
        self.pad_input_row.add_css_class("property")
        control.add(self.pad_input_row)

        page.add(control)

        actions = Adw.PreferencesGroup()
        rescan = Gtk.Button(label="Jetzt neu suchen", halign=Gtk.Align.CENTER)
        rescan.add_css_class("pill")
        rescan.add_css_class("suggested-action")
        rescan.connect("clicked", lambda *_: self.emit("rescan-requested"))
        actions.add(rescan)
        page.add(actions)
        return page

    def _artwork_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Bilder & Daten",
                                   icon_name="image-x-generic-symbolic")

        group = Adw.PreferencesGroup(
            title="Cover und Banner",
            description="Vorhandene Bilder der Launcher werden immer zuerst benutzt.",
        )
        fetch = Adw.SwitchRow(
            title="Bilder online nachladen",
            subtitle="Steam-CDN und, falls eingerichtet, SteamGridDB",
            active=self.settings["fetch_covers"],
        )
        fetch.connect("notify::active",
                      lambda row, *_: self._set("fetch_covers", row.get_active()))
        group.add(fetch)

        metadata = Adw.SwitchRow(
            title="Metadaten laden",
            subtitle="Kategorien, Publisher, Erscheinungsdatum und Kurzbeschreibung "
                     "aus dem Steam-Store",
            active=self.settings["fetch_metadata"],
        )
        metadata.connect("notify::active",
                         lambda row, *_: self._set("fetch_metadata", row.get_active()))
        group.add(metadata)

        self.key_row = Adw.PasswordEntryRow(title="SteamGridDB API-Schlüssel")
        self.key_row.set_text(self.settings["steamgriddb_key"])
        self.key_row.connect("changed", self._on_key_changed)
        group.add(self.key_row)

        hint = Adw.ActionRow(
            title="Schlüssel holen",
            subtitle="steamgriddb.com/profile/preferences/api",
        )
        link = Gtk.LinkButton(uri="https://www.steamgriddb.com/profile/preferences/api",
                              label="Öffnen", valign=Gtk.Align.CENTER)
        hint.add_suffix(link)
        group.add(hint)
        page.add(group)

        actions = Adw.PreferencesGroup(
            description="Sucht für alle Spiele ohne Bild erneut nach einem Cover."
        )
        refetch = Gtk.Button(label="Fehlende Cover suchen", halign=Gtk.Align.CENTER)
        refetch.add_css_class("pill")
        refetch.connect("clicked", lambda *_: self.emit("covers-requested"))
        actions.add(refetch)
        page.add(actions)
        return page

    # --- callbacks ----------------------------------------------------------

    def _refresh_pads(self) -> bool:
        if self.pads is None:
            self.pad_row.set_subtitle("Controller-Unterstützung ist aus")
            return True
        names = self.pads.names()
        self.pad_row.set_subtitle(
            "\n".join(names) if names
            else "keiner gefunden — ist er eingeschaltet und verbunden?"
        )
        if self.pads.last_action:
            self.pad_input_row.set_subtitle(
                f"{self.pads.last_action}"
                + (f"  ({self.pads.last_device})" if self.pads.last_device else "")
            )
        return True

    def _set(self, key: str, value) -> None:
        self.settings[key] = value

    def _on_source_toggled(self, row, _param, key: str) -> None:
        self.settings.set_source(key, row.get_active())

    def _on_key_changed(self, row) -> None:
        self.settings["steamgriddb_key"] = row.get_text().strip()
