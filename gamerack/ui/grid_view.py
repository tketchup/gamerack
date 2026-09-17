"""The default view: a grid of covers, the way Cartridges shows them."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk  # noqa: E402

from ..models import Game
from .widgets import GameCard, LazyCovers


class GridView(Adw.Bin):
    __gtype_name__ = "GamerackGridView"

    __gsignals__ = {
        "game-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-details": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-menu": (GObject.SignalFlags.RUN_FIRST, None, (str, float, float)),
    }

    def __init__(self, cover_width: int = 200):
        super().__init__()
        self.cover_width = cover_width
        self.cards: dict[str, GameCard] = {}

        # Not homogeneous: cards have an exact width, so letting the box centre
        # them keeps every cover the same size instead of stretching the last
        # column to fill the window.
        self.flowbox = Gtk.FlowBox(
            valign=Gtk.Align.START,
            halign=Gtk.Align.CENTER,
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=False,
            row_spacing=18,
            column_spacing=18,
            min_children_per_line=1,
            max_children_per_line=16,
        )
        # Enter on a focused cell does what a click does.
        self.flowbox.connect(
            "child-activated",
            lambda _fb, child: self.emit("game-details", child.get_child().game.game_id),
        )
        self.flowbox.add_css_class("game-grid")
        self.flowbox.set_margin_start(18)
        self.flowbox.set_margin_end(18)
        self.flowbox.set_margin_top(18)
        self.flowbox.set_margin_bottom(24)

        # Adw.Clamp, not ClampScrollable: GtkFlowBox is not a GtkScrollable, and
        # pairing it with the scrollable clamp breaks height-for-width.
        clamp = Adw.Clamp(maximum_size=2200, tightening_threshold=1600,
                          child=self.flowbox)
        self.scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vexpand=True,
            child=clamp,
        )
        self.lazy = LazyCovers(self.scroller)

        self.empty = Adw.StatusPage(
            icon_name="applications-games-symbolic",
            title="Keine Spiele",
            description="Starte einen Suchlauf oder passe die Quellen in den "
                        "Einstellungen an.",
        )

        self.stack = Gtk.Stack()
        self.stack.add_named(self.scroller, "grid")
        self.stack.add_named(self.empty, "empty")
        self.set_child(self.stack)

    # --- population ---------------------------------------------------------

    def set_games(self, games: list[Game]) -> None:
        child = self.flowbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.flowbox.remove(child)
            child = nxt
        self.cards.clear()

        for game in games:
            card = GameCard(
                game, self.cover_width,
                on_play=lambda g: self.emit("game-activated", g.game_id),
                on_info=lambda g: self.emit("game-details", g.game_id),
            )
            self._attach_gestures(card, game)
            self.cards[game.game_id] = card

            holder = Gtk.FlowBoxChild(child=card, focusable=True)
            holder.add_css_class("game-cell")
            self.flowbox.append(holder)

        self.stack.set_visible_child_name("grid" if games else "empty")
        self.lazy.set_cards(list(self.cards.values()))

    def set_cover_width(self, width: int) -> None:
        self.cover_width = width
        for card in self.cards.values():
            card.set_width(width)
        self.lazy.schedule()

    def refresh_cover(self, game: Game) -> None:
        card = self.cards.get(game.game_id)
        if card is not None:
            card.cover.refresh()
            card.update()

    # --- input --------------------------------------------------------------

    def _attach_gestures(self, card: GameCard, game: Game) -> None:
        click = Gtk.GestureClick(button=1)
        click.connect("released", self._on_click, game)
        card.add_controller(click)

        secondary = Gtk.GestureClick(button=3)
        secondary.connect("pressed", self._on_secondary, card, game)
        card.add_controller(secondary)

        long_press = Gtk.GestureLongPress()
        long_press.connect("pressed", self._on_secondary_lp, card, game)
        card.add_controller(long_press)

    def _on_click(self, gesture, n_press, x, y, game):
        # A click opens the game, it does not start it: the hover play button
        # and Enter do that. Too many libraries here are "what even is this?"
        # rather than "start it right now".
        if n_press == 1:
            self.emit("game-details", game.game_id)

    def _on_secondary(self, gesture, n_press, x, y, card, game):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._popup(card, game, x, y)

    def _on_secondary_lp(self, gesture, x, y, card, game):
        self._popup(card, game, x, y)

    def _popup(self, card, game, x, y):
        ok, bounds = card.compute_bounds(self)
        ox, oy = (bounds.origin.x, bounds.origin.y) if ok else (0, 0)
        self.emit("game-menu", game.game_id, ox + x, oy + y)
