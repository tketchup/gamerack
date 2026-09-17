"""Steam-style view: a compact list whose rows expand into short details."""

from __future__ import annotations

import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk, Pango  # noqa: E402

from ..launchers import launcher_for
from ..models import Game, humanise_playtime
from .widgets import Cover, LazyCovers

ROW_COVER = 46
DETAIL_COVER = 150


class GameRow(Gtk.ListBoxRow):
    """One collapsed line that reveals a details panel when clicked."""

    def __init__(self, game: Game, view: "ListView"):
        super().__init__()
        self.game = game
        self.view = view
        self.expanded = False
        self.add_css_class("game-row")

        self.cover = Cover(game, ROW_COVER)
        self.cover.add_css_class("row-cover")

        self.name_label = Gtk.Label(label=game.name, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.name_label.add_css_class("row-title")
        self.source_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.source_label.add_css_class("row-subtitle")

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1,
                         valign=Gtk.Align.CENTER, hexpand=True)
        labels.append(self.name_label)
        labels.append(self.source_label)

        self.chevron = Gtk.Image(icon_name="go-next-symbolic")
        self.chevron.add_css_class("row-chevron")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.add_css_class("row-header")
        header.append(self.cover)
        header.append(labels)
        header.append(self.chevron)

        self.details = self._build_details()
        self.revealer = Gtk.Revealer(
            child=self.details,
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            transition_duration=200,
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(self.revealer)
        self.set_child(box)

        self.update()

    def _build_details(self) -> Gtk.Widget:
        self.detail_cover = Cover(self.game, DETAIL_COVER)
        self.detail_cover.set_valign(Gtk.Align.START)

        self.meta = Gtk.Label(xalign=0, wrap=True, yalign=0)
        self.meta.add_css_class("row-meta")

        play = Gtk.Button()
        play.set_child(Adw.ButtonContent(icon_name="media-playback-start-symbolic",
                                        label="Spielen"))
        play.add_css_class("suggested-action")
        play.set_sensitive(bool(self.game.command))
        play.connect("clicked", lambda *_: self.view.emit("game-activated",
                                                          self.game.game_id))

        details = Gtk.Button(icon_name="dialog-information-symbolic",
                             tooltip_text="Großansicht")
        details.connect("clicked", lambda *_: self.view.emit("game-details",
                                                             self.game.game_id))

        edit = Gtk.Button(icon_name="document-edit-symbolic",
                          tooltip_text="Details bearbeiten")
        edit.connect("clicked", lambda *_: self.view.emit("game-edit",
                                                          self.game.game_id))

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                          halign=Gtk.Align.START)
        buttons.append(play)
        buttons.append(details)
        buttons.append(edit)

        launcher = launcher_for(self.game.source)
        if launcher is not None:
            open_launcher = Gtk.Button()
            open_launcher.set_child(
                Adw.ButtonContent(icon_name="external-link-symbolic", label=launcher[0])
            )
            open_launcher.set_tooltip_text(
                f"{launcher[0]} öffnen, ohne das Spiel zu starten"
            )
            open_launcher.connect(
                "clicked",
                lambda *_: self.view.emit("game-launcher", self.game.game_id),
            )
            buttons.append(open_launcher)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                        hexpand=True, valign=Gtk.Align.START)
        right.append(self.meta)
        right.append(buttons)

        panel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        panel.add_css_class("row-details")
        panel.append(self.detail_cover)
        panel.append(right)
        return panel

    def update(self) -> None:
        self.name_label.set_label(self.game.name)
        subtitle = self.game.source_label or self.game.source
        if not self.game.installed:
            subtitle += " · nicht installiert"
        self.source_label.set_label(subtitle)

        lines = [f"Quelle: {self.game.source_label or self.game.source}"]
        if self.game.developer:
            lines.append(f"Entwickler: {self.game.developer}")
        if self.game.categories:
            lines.append("Kategorien: " + ", ".join(self.game.categories))
        if self.game.release_date:
            lines.append(f"Erschienen: {self.game.release_date}")
        lines.append(f"Status: {'installiert' if self.game.installed else 'nicht installiert'}")
        lines.append(humanise_playtime(self.game.play_seconds).capitalize())
        if self.game.last_played:
            lines.append("Zuletzt gespielt: "
                         + time.strftime("%d.%m.%Y, %H:%M",
                                         time.localtime(self.game.last_played)))
        if self.game.install_dir:
            lines.append(f"Ordner: {self.game.install_dir}")
        self.meta.set_label("\n".join(lines))

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        self.revealer.set_reveal_child(expanded)
        self.chevron.set_from_icon_name(
            "go-down-symbolic" if expanded else "go-next-symbolic"
        )
        if expanded:
            self.update()
            self.cover.load()
            self.detail_cover.load()
            self.add_css_class("expanded")
        else:
            self.remove_css_class("expanded")

    def refresh_cover(self) -> None:
        self.cover.refresh()
        self.detail_cover.refresh()


class ListView(Adw.Bin):
    __gtype_name__ = "GamerackListView"

    __gsignals__ = {
        "game-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-details": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-edit": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-launcher": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-menu": (GObject.SignalFlags.RUN_FIRST, None, (str, float, float)),
    }

    def __init__(self):
        super().__init__()
        self.rows: dict[str, GameRow] = {}
        self._expanded: GameRow | None = None

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                   valign=Gtk.Align.START)
        self.listbox.add_css_class("game-list")
        self.listbox.add_css_class("boxed-list")
        self.listbox.connect("row-activated", self._on_row_activated)

        clamp = Adw.Clamp(maximum_size=900, tightening_threshold=700,
                          child=self.listbox, margin_start=12, margin_end=12,
                          margin_top=12, margin_bottom=24)
        self.scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=clamp
        )
        self.lazy = LazyCovers(self.scroller, margin=400)

        self.empty = Adw.StatusPage(
            icon_name="applications-games-symbolic",
            title="Keine Spiele",
            description="Starte einen Suchlauf, um deine Bibliothek zu füllen.",
        )
        self.stack = Gtk.Stack()
        self.stack.add_named(self.scroller, "list")
        self.stack.add_named(self.empty, "empty")
        self.set_child(self.stack)

    def set_games(self, games: list[Game]) -> None:
        self.listbox.remove_all()
        self.rows.clear()
        self._expanded = None

        for game in games:
            row = GameRow(game, self)
            secondary = Gtk.GestureClick(button=3)
            secondary.connect("pressed", self._on_secondary, row)
            row.add_controller(secondary)
            self.listbox.append(row)
            self.rows[game.game_id] = row

        self.stack.set_visible_child_name("list" if games else "empty")
        # Rows carry two Cover widgets rather than a GameCard, so drive them
        # through a tiny adapter instead of the shared card list.
        self.lazy.set_cards([_RowAdapter(row) for row in self.rows.values()])

    def refresh_cover(self, game: Game) -> None:
        row = self.rows.get(game.game_id)
        if row is not None:
            row.refresh_cover()
            row.update()

    def _on_row_activated(self, listbox, row: GameRow) -> None:
        if self._expanded is not None and self._expanded is not row:
            self._expanded.set_expanded(False)
        row.set_expanded(not row.expanded)
        self._expanded = row if row.expanded else None

    def _on_secondary(self, gesture, n_press, x, y, row: GameRow) -> None:
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        ok, bounds = row.compute_bounds(self)
        ox, oy = (bounds.origin.x, bounds.origin.y) if ok else (0, 0)
        self.emit("game-menu", row.game.game_id, ox + x, oy + y)


class _RowAdapter:
    """Lets LazyCovers drive a GameRow, which has no single `cover` card."""

    def __init__(self, row: GameRow):
        self.row = row
        self.cover = _CoverPair(row)

    def compute_bounds(self, target):
        return self.row.compute_bounds(target)


class _CoverPair:
    def __init__(self, row: GameRow):
        self.row = row

    def load(self):
        self.row.cover.load()
        if self.row.expanded:
            self.row.detail_cover.load()

    def unload(self):
        self.row.cover.unload()
        self.row.detail_cover.unload()
