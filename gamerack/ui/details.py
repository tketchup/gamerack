"""The per-game details dialog, where the user can override what we detected."""

from __future__ import annotations

import shlex
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk  # noqa: E402

from ..covers import banner_file, cover_file, save_artwork
from ..models import Game
from .artwork_picker import ArtworkPickerDialog
from .widgets import TEXTURES, Banner, Cover


class GameDetailsDialog(Adw.Dialog):
    __gtype_name__ = "GamerackGameDetails"

    __gsignals__ = {
        "saved": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "artwork-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "removed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, game: Game, library, settings):
        super().__init__()
        self.game = game
        self.library = library
        self.settings = settings
        self.set_title("Spiel bearbeiten")
        self.set_content_width(480)
        self.set_content_height(700)

        header = Adw.HeaderBar(show_end_title_buttons=False,
                               show_start_title_buttons=False)
        cancel = Gtk.Button(label="Abbrechen")
        cancel.connect("clicked", lambda *_: self.close())
        apply_button = Gtk.Button(label="Übernehmen")
        apply_button.add_css_class("suggested-action")
        apply_button.connect("clicked", self._on_apply)
        header.pack_start(cancel)
        header.pack_end(apply_button)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self._build_body())
        self.set_child(toolbar)

    # --- layout -------------------------------------------------------------

    def _build_body(self) -> Gtk.Widget:
        self.cover = Cover(self.game, 190)
        self.cover.set_halign(Gtk.Align.CENTER)
        self.cover.load()

        delete_cover = Gtk.Button(icon_name="user-trash-symbolic",
                                  tooltip_text="Cover entfernen")
        delete_cover.add_css_class("circular")
        delete_cover.add_css_class("osd")
        delete_cover.connect("clicked", self._on_delete_cover)

        pick_cover = Gtk.Button(icon_name="document-edit-symbolic",
                                tooltip_text="Cover aus Datei wählen")
        pick_cover.add_css_class("circular")
        pick_cover.add_css_class("osd")
        pick_cover.connect("clicked", self._on_pick_cover)

        find_cover = Gtk.Button(icon_name="system-search-symbolic",
                                tooltip_text="Cover online suchen")
        find_cover.add_css_class("circular")
        find_cover.add_css_class("osd")
        find_cover.connect("clicked", lambda *_: self._open_picker("cover"))

        cover_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                                halign=Gtk.Align.CENTER, valign=Gtk.Align.END,
                                margin_bottom=14)
        for button in (delete_cover, pick_cover, find_cover):
            cover_buttons.append(button)

        cover_overlay = Gtk.Overlay(child=self.cover, halign=Gtk.Align.CENTER,
                                    margin_top=18)
        cover_overlay.add_overlay(cover_buttons)

        banner_overlay = self._build_banner()

        self.title_row = Adw.EntryRow(title="Titel", text=self.game.name)
        self.developer_row = Adw.EntryRow(title="Entwickler (optional)",
                                          text=self.game.developer)
        self.command_row = Adw.EntryRow(
            title="Befehl", text=shlex.join(self.game.command) if self.game.command else ""
        )

        browse = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text="Ausführbare Datei wählen")
        browse.add_css_class("flat")
        browse.connect("clicked", self._on_browse_executable)
        self.command_row.add_suffix(browse)

        group = Adw.PreferencesGroup()
        group.add(self.title_row)
        group.add(self.developer_row)
        group.add(self.command_row)

        info = Adw.PreferencesGroup(title="Erkannt")
        info.add(self._readonly("Quelle", self.game.source_label or self.game.source))
        if self.game.categories:
            info.add(self._readonly("Kategorien", ", ".join(self.game.categories)))
        if self.game.publisher:
            info.add(self._readonly("Publisher", self.game.publisher))
        if self.game.release_date:
            info.add(self._readonly("Erschienen", self.game.release_date))
        info.add(self._readonly("Kennung", self.game.game_id))
        if self.game.install_dir:
            info.add(self._readonly("Ordner", self.game.install_dir))

        self.hidden_row = Adw.SwitchRow(
            title="Ausblenden",
            subtitle="Versteckt das Spiel in allen Ansichten",
            active=self.game.hidden,
        )
        actions = Adw.PreferencesGroup()
        actions.add(self.hidden_row)

        remove = Gtk.Button(label="Aus Bibliothek entfernen")
        remove.add_css_class("destructive-action")
        remove.set_margin_top(6)
        remove.connect("clicked", self._on_remove)
        actions.add(remove)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                       margin_start=18, margin_end=18, margin_bottom=24)
        page.append(cover_overlay)
        page.append(banner_overlay)
        page.append(group)
        page.append(info)
        page.append(actions)

        return Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=page)

    def _build_banner(self) -> Gtk.Widget:
        """The wide artwork used by the showcase hero and the detail page."""
        self.banner = Banner(self.game, height=96)

        caption = Gtk.Label(label="Banner", xalign=0, valign=Gtk.Align.START,
                            margin_start=10, margin_top=8)
        caption.add_css_class("hero-subtitle")

        delete = Gtk.Button(icon_name="user-trash-symbolic",
                            tooltip_text="Banner entfernen")
        search = Gtk.Button(icon_name="system-search-symbolic",
                            tooltip_text="Banner online suchen")
        for button, handler in ((delete, self._on_delete_banner),
                                (search, lambda *_: self._open_picker("banner"))):
            button.add_css_class("circular")
            button.add_css_class("osd")
            button.connect("clicked", handler)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                          halign=Gtk.Align.END, valign=Gtk.Align.CENTER,
                          margin_end=10)
        buttons.append(delete)
        buttons.append(search)

        overlay = Gtk.Overlay(child=self.banner)
        overlay.add_overlay(caption)
        overlay.add_overlay(buttons)
        overlay.set_overflow(Gtk.Overflow.HIDDEN)
        overlay.add_css_class("banner-edit")
        return overlay

    def _open_picker(self, kind: str) -> None:
        picker = ArtworkPickerDialog(self.game, self.settings, kind)
        picker.connect("chosen", self._on_artwork_chosen)
        picker.present(self)

    def _on_artwork_chosen(self, _picker, game_id: str, kind: str) -> None:
        if kind == "banner":
            self.banner.refresh()
        else:
            self.cover.refresh()
        self.library.save()
        self.emit("artwork-changed", game_id)

    def _on_delete_banner(self, _button) -> None:
        path = banner_file(self.game)
        TEXTURES.drop(str(path))
        if self.game.banner_path:
            TEXTURES.drop(self.game.banner_path)
        path.unlink(missing_ok=True)
        self.game.banner_path = ""
        if "banner_path" in self.game.overrides:
            self.game.overrides.remove("banner_path")
        self.banner.refresh()
        self.emit("artwork-changed", self.game.game_id)

    def _readonly(self, title: str, value: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title, subtitle=value)
        row.add_css_class("property")
        row.set_subtitle_selectable(True)
        return row

    # --- cover actions ------------------------------------------------------

    def _on_delete_cover(self, _button) -> None:
        path = cover_file(self.game)
        TEXTURES.drop(str(path))
        if self.game.cover_path:
            TEXTURES.drop(self.game.cover_path)
        path.unlink(missing_ok=True)
        self.game.cover_path = ""
        # Drop the override too, so a later scan or fetch may supply a new one.
        if "cover_path" in self.game.overrides:
            self.game.overrides.remove("cover_path")
        self.cover.unload()
        self.emit("artwork-changed", self.game.game_id)

    def _on_pick_cover(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Cover wählen")
        images = Gtk.FileFilter(name="Bilder")
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
            images.add_pattern(pattern)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(images)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_cover_chosen)

    def _on_cover_chosen(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        path = file.get_path()
        if not path:
            return
        TEXTURES.drop(str(cover_file(self.game)))
        saved = save_artwork(self.game, Path(path), "cover")
        if saved:
            self.game.set_override("cover_path", saved)
            self.cover.refresh()
            self.emit("artwork-changed", self.game.game_id)

    # --- executable ---------------------------------------------------------

    def _on_browse_executable(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Ausführbare Datei wählen")
        dialog.open(self.get_root(), None, self._on_executable_chosen)

    def _on_executable_chosen(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if file.get_path():
            self.command_row.set_text(shlex.quote(file.get_path()))

    # --- save / remove ------------------------------------------------------

    def _on_apply(self, _button) -> None:
        name = self.title_row.get_text().strip()
        if name and name != self.game.name:
            self.game.set_override("name", name)

        developer = self.developer_row.get_text().strip()
        if developer != self.game.developer:
            self.game.set_override("developer", developer)

        text = self.command_row.get_text().strip()
        try:
            command = shlex.split(text)
        except ValueError:
            command = []
        if command and command != self.game.command:
            self.game.set_override("command", command)

        if self.hidden_row.get_active() != self.game.hidden:
            self.game.set_override("hidden", self.hidden_row.get_active())

        self.library.save()
        self.emit("saved", self.game.game_id)
        self.close()

    def _on_remove(self, _button) -> None:
        confirm = Adw.AlertDialog(
            heading="Spiel entfernen?",
            body=f"„{self.game.name}“ wird aus deiner Bibliothek entfernt. "
                 "Ein erneuter Suchlauf kann es wieder hinzufügen, sofern die "
                 "Quelle es weiterhin meldet.",
        )
        confirm.add_response("cancel", "Abbrechen")
        confirm.add_response("remove", "Entfernen")
        confirm.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_default_response("cancel")
        confirm.connect("response", self._on_remove_response)
        confirm.present(self)

    def _on_remove_response(self, dialog, response: str) -> None:
        if response != "remove":
            return
        cover_file(self.game).unlink(missing_ok=True)
        banner_file(self.game).unlink(missing_ok=True)
        self.library.remove(self.game.game_id)
        self.library.save()
        self.emit("removed", self.game.game_id)
        self.close()
