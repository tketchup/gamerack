"""Pick artwork by hand: search several sources and show what they offer."""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from ..covers import artwork_file, save_artwork, search_artwork
from ..models import Game
from .widgets import TEXTURES, Thumbnail

THUMB = {"cover": (132, 198), "banner": (272, 88)}


class ArtworkPickerDialog(Adw.Dialog):
    """Shows candidate images for one game and applies the one that is clicked."""

    __gtype_name__ = "GamerackArtworkPicker"

    __gsignals__ = {
        # game_id, kind ("cover" or "banner")
        "chosen": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
    }

    def __init__(self, game: Game, settings, kind: str = "cover"):
        super().__init__()
        self.game = game
        self.settings = settings
        self.kind = kind
        self.generation = 0
        self.results = 0

        noun = "Banner" if kind == "banner" else "Cover"
        self.set_title(f"{noun} suchen")
        self.set_content_width(720)
        self.set_content_height(620)

        header = Adw.HeaderBar()
        from_file = Gtk.Button(icon_name="document-open-symbolic",
                               tooltip_text=f"{noun} aus einer Datei wählen")
        from_file.connect("clicked", self._on_pick_file)
        header.pack_end(from_file)

        self.entry = Gtk.SearchEntry(placeholder_text="Suchbegriff",
                                     text=game.name, hexpand=True)
        self.entry.connect("activate", lambda *_: self.search())
        search_button = Gtk.Button(label="Suchen")
        search_button.add_css_class("suggested-action")
        search_button.connect("clicked", lambda *_: self.search())

        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                             margin_start=14, margin_end=14,
                             margin_top=12, margin_bottom=6)
        search_row.append(self.entry)
        search_row.append(search_button)

        self.flowbox = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
            valign=Gtk.Align.START, halign=Gtk.Align.CENTER,
            row_spacing=14, column_spacing=14, max_children_per_line=8,
            margin_start=14, margin_end=14, margin_top=8, margin_bottom=14,
        )
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      vexpand=True, child=self.flowbox)

        self.spinner_page = Adw.StatusPage(title="Wird gesucht …")
        self.spinner_page.set_child(Adw.Spinner(width_request=32, height_request=32))

        self.empty_page = Adw.StatusPage(
            icon_name="image-missing-symbolic",
            title="Nichts gefunden",
            description="Versuche einen kürzeren Suchbegriff — oft reicht der "
                        "Haupttitel ohne Untertitel und Jahreszahl.",
        )

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(scroller, "results")
        self.stack.add_named(self.spinner_page, "searching")
        self.stack.add_named(self.empty_page, "empty")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(search_row)
        if not settings["steamgriddb_key"]:
            hint = Adw.Banner(
                title="Mehr Auswahl mit einem SteamGridDB-Schlüssel "
                      "(Einstellungen → Cover)",
                revealed=True,
            )
            body.append(hint)
        body.append(self.stack)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(body)
        self.set_child(toolbar)

        self.connect("closed", lambda *_: self._cancel())
        self.search()

    # --- searching ----------------------------------------------------------

    def _cancel(self) -> None:
        self.generation += 1

    def search(self) -> None:
        self._cancel()
        generation = self.generation
        term = self.entry.get_text().strip() or self.game.name

        self._clear()
        self.results = 0
        self.stack.set_visible_child_name("searching")

        def deliver(label: str, data: bytes) -> None:
            GLib.idle_add(self._add_result, generation, label, data)

        def work():
            try:
                search_artwork(
                    self.game, term, self.kind,
                    self.settings["steamgriddb_key"],
                    on_item=deliver,
                    should_stop=lambda: generation != self.generation,
                )
            finally:
                GLib.idle_add(self._finished, generation)

        threading.Thread(target=work, daemon=True, name="artwork-search").start()

    def _clear(self) -> None:
        child = self.flowbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.flowbox.remove(child)
            child = nxt

    def _add_result(self, generation: int, label: str, data: bytes) -> bool:
        if generation != self.generation:
            return False
        try:
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
        except GLib.Error:
            return False

        width, height = THUMB[self.kind]
        picture = Thumbnail(texture, width, height)

        caption = Gtk.Label(label=label)
        caption.add_css_class("row-subtitle")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.append(picture)
        box.append(caption)

        button = Gtk.Button(child=box)
        button.add_css_class("flat")
        button.add_css_class("artwork-choice")
        button.connect("clicked", self._on_chosen, data)

        self.flowbox.append(button)
        self.results += 1
        self.stack.set_visible_child_name("results")
        return False

    def _finished(self, generation: int) -> bool:
        if generation != self.generation:
            return False
        if not self.results:
            self.stack.set_visible_child_name("empty")
        return False

    # --- applying -----------------------------------------------------------

    def _apply(self, data) -> None:
        TEXTURES.drop(str(artwork_file(self.game, self.kind)))
        current = (self.game.banner_path if self.kind == "banner"
                   else self.game.cover_path)
        if current:
            TEXTURES.drop(current)

        saved = save_artwork(self.game, data, self.kind)
        if not saved:
            return
        field = "banner_path" if self.kind == "banner" else "cover_path"
        self.game.set_override(field, saved)
        self.emit("chosen", self.game.game_id, self.kind)
        self.close()

    def _on_chosen(self, _button, data: bytes) -> None:
        self._apply(data)

    def _on_pick_file(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Bild wählen")
        images = Gtk.FileFilter(name="Bilder")
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
            images.add_pattern(pattern)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(images)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if file.get_path():
            self._apply(Path(file.get_path()))
