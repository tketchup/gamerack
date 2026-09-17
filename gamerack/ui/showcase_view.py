"""PS5-style view: one hero banner above a horizontal strip of covers."""

from __future__ import annotations

import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from ..launchers import launcher_for
from ..models import Game, humanise_playtime
from .widgets import Banner, GameCard, LazyCovers

FOCUSED_WIDTH = 230
RESTING_WIDTH = 140
SPACING = 16

# Where the selected cover sits. Measured in covers rather than as a fraction of
# the window: exactly one game fits fully to its left, with the edge of the one
# before it just showing so it is clear the row continues. The strip is padded
# on both sides so that every game — the first and the last included — can
# reach this same spot.
PEEK = 22
ANCHOR = PEEK + RESTING_WIDTH + 2 * SPACING


class ShowcaseView(Adw.Bin):
    __gtype_name__ = "GamerackShowcaseView"

    __gsignals__ = {
        "game-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-details": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-edit": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-launcher": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-focused": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "game-menu": (GObject.SignalFlags.RUN_FIRST, None, (str, float, float)),
    }

    def __init__(self):
        super().__init__()
        self.games: list[Game] = []
        self.cards: list[GameCard] = []
        self.index = 0
        self.add_css_class("showcase")

        self._build_hero()
        self._build_strip()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.hero)
        box.append(self.strip_scroller)

        self.empty = Adw.StatusPage(
            icon_name="applications-games-symbolic",
            title="Keine Spiele",
            description="Starte einen Suchlauf, um deine Bibliothek zu füllen.",
        )
        self.stack = Gtk.Stack()
        self.stack.add_named(box, "showcase")
        self.stack.add_named(self.empty, "empty")
        self.set_child(self.stack)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.set_focusable(True)

    # --- construction -------------------------------------------------------

    def _build_hero(self) -> None:
        # A banner, not the stretched cover: a 2:3 poster blown up to fill a
        # wide frame is mostly a crop of somebody's chin.
        self.hero_image = Banner(height=300)

        self.hero_title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.hero_title.add_css_class("hero-title")
        self.hero_subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.hero_subtitle.add_css_class("hero-subtitle")

        self.play_button = Gtk.Button()
        self.play_button.set_child(
            Adw.ButtonContent(icon_name="media-playback-start-symbolic", label="Spielen")
        )
        self.play_button.add_css_class("suggested-action")
        self.play_button.add_css_class("pill")
        self.play_button.connect("clicked", lambda *_: self._activate_current())

        self.edit_button = Gtk.Button()
        self.edit_button.set_child(
            Adw.ButtonContent(icon_name="document-edit-symbolic", label="Bearbeiten")
        )
        self.edit_button.add_css_class("pill")
        self.edit_button.connect("clicked", lambda *_: self._emit_current("game-edit"))

        self.info_button = Gtk.Button(icon_name="dialog-information-symbolic",
                                      tooltip_text="Großansicht")
        self.info_button.add_css_class("circular")
        self.info_button.connect("clicked",
                                 lambda *_: self._emit_current("game-details"))

        self.launcher_button = Gtk.Button()
        self.launcher_content = Adw.ButtonContent(icon_name="external-link-symbolic",
                                                  label="Launcher")
        self.launcher_button.set_child(self.launcher_content)
        self.launcher_button.add_css_class("pill")
        self.launcher_button.connect("clicked",
                                     lambda *_: self._emit_current("game-launcher"))

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                          halign=Gtk.Align.START)
        for button in (self.play_button, self.edit_button, self.launcher_button,
                       self.info_button):
            buttons.append(button)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       valign=Gtk.Align.END, hexpand=True)
        info.add_css_class("hero-info")
        info.append(self.hero_title)
        info.append(self.hero_subtitle)
        info.append(buttons)

        scrim = Gtk.Box()
        scrim.add_css_class("hero-scrim")

        overlay = Gtk.Overlay(child=self.hero_image)
        overlay.add_overlay(scrim)
        overlay.add_overlay(info)

        self.hero = overlay
        self.hero.add_css_class("hero")
        self.hero.set_size_request(-1, 300)
        self.hero.set_vexpand(True)
        self.hero.set_overflow(Gtk.Overflow.HIDDEN)

    def _build_strip(self) -> None:
        self.strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=SPACING,
                             valign=Gtk.Align.CENTER)
        self.strip.add_css_class("showcase-strip")
        self.strip.set_margin_top(18)
        self.strip.set_margin_bottom(24)

        # Spacers rather than margins: a scrollable child whose margins exceed
        # the viewport makes GTK complain that it is being measured for less
        # than its minimum. Widgets inside the box are simply part of its width.
        self.lead_spacer = Gtk.Box()
        self.trail_spacer = Gtk.Box()
        self._padding = (0, 0)

        self.strip_scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            child=self.strip,
        )
        self.strip_scroller.set_size_request(-1, FOCUSED_WIDTH * 3 // 2 + 60)
        self.lazy = LazyCovers(self.strip_scroller, margin=900)

        # "changed" fires whenever the page size or the content width moves,
        # which is exactly when the padding needs recomputing.
        self.strip_scroller.get_hadjustment().connect("changed", self._update_padding)

        # A wheel is vertical, the strip is horizontal, so map one to the other.
        # Scrolling moves the selection rather than just the view: the whole
        # point of the anchor is that the chosen game stays put.
        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        scroll.connect("scroll", self._on_scroll)
        self.strip_scroller.add_controller(scroll)
        self._scroll_accumulator = 0.0

    # --- population ---------------------------------------------------------

    def set_games(self, games: list[Game]) -> None:
        child = self.strip.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.strip.remove(child)
            child = nxt

        self.games = games
        self.cards = []
        self.strip.append(self.lead_spacer)
        for position, game in enumerate(games):
            card = GameCard(game, RESTING_WIDTH, show_title=False)
            card.add_css_class("showcase-card")
            # Centred rather than filled: a card stretched to the strip's height
            # would drag its cover out of shape, which is what made the resting
            # tiles look oversized.
            card.set_valign(Gtk.Align.CENTER)
            card.set_halign(Gtk.Align.CENTER)
            self._attach_gestures(card, position)
            self.strip.append(card)
            self.cards.append(card)
        self.strip.append(self.trail_spacer)

        self.stack.set_visible_child_name("showcase" if games else "empty")
        self.index = min(self.index, max(0, len(games) - 1))
        self.lazy.set_cards(self.cards)
        if games:
            self.select(self.index, scroll=False)

    def refresh_cover(self, game: Game) -> None:
        for position, card in enumerate(self.cards):
            if card.game.game_id == game.game_id:
                card.cover.refresh()
                if position == self.index:
                    self.hero_image.refresh()
                break

    def refresh_game(self, game: Game) -> None:
        """New metadata arrived; redraw the hero if this is the game on show."""
        if self.games and self.games[self.index].game_id == game.game_id:
            self._update_hero()

    # --- selection ----------------------------------------------------------

    def select(self, index: int, scroll: bool = True) -> None:
        if not self.games:
            return
        index = max(0, min(index, len(self.games) - 1))
        for position, card in enumerate(self.cards):
            focused = position == index
            card.set_width(FOCUSED_WIDTH if focused else RESTING_WIDTH)
            if focused:
                card.add_css_class("focused")
                card.cover.load()
            else:
                card.remove_css_class("focused")
        self.index = index
        self._update_hero()
        if scroll:
            GLib.idle_add(self._scroll_into_view)

    def _update_padding(self, adjustment) -> None:
        """Pad the strip so any game can sit exactly on the anchor."""
        page = adjustment.get_page_size()
        if page <= 0:
            return
        # Never past the middle: on a narrow window a fixed anchor would push
        # everything that follows off the right edge.
        lead = max(24, min(ANCHOR, round(page / 2)))
        trail = max(24, round(page - lead - FOCUSED_WIDTH))
        if (lead, trail) == self._padding:
            return                       # else resizing the spacers would loop
        self._padding = (lead, trail)
        # Applied from idle, not here: "changed" arrives in the middle of the
        # scrolled window's allocation, and resizing a child at that point makes
        # GTK measure the strip against a width it has already moved on from.
        GLib.idle_add(self._apply_padding)

    def _apply_padding(self) -> bool:
        lead, trail = self._padding
        # The spacers sit inside the box, so the strip's own spacing is added on
        # either side of them; take that off again to land exactly on the anchor.
        self.lead_spacer.set_size_request(max(1, lead - SPACING), -1)
        self.trail_spacer.set_size_request(max(1, trail - SPACING), -1)
        GLib.idle_add(self._scroll_into_view)
        return False

    def _scroll_into_view(self) -> bool:
        if not self.cards:
            return False
        card = self.cards[self.index]
        ok, bounds = card.compute_bounds(self.strip)
        if not ok:
            return False
        adjustment = self.strip_scroller.get_hadjustment()
        # The leading spacer is part of the strip, so the card's position within
        # it already counts the anchor offset in; take it back off to get the
        # scroll value that puts the card exactly on the anchor.
        target = bounds.origin.x - self._padding[0]
        target = max(adjustment.get_lower(),
                     min(target, adjustment.get_upper() - adjustment.get_page_size()))
        adjustment.set_value(target)
        return False

    def _on_scroll(self, _controller, dx: float, dy: float) -> bool:
        # Trackpads deliver many small deltas; collect them until they add up to
        # one step so a light flick does not race through twenty games.
        self._scroll_accumulator += dx if abs(dx) > abs(dy) else dy
        while self._scroll_accumulator >= 1.0:
            self._scroll_accumulator -= 1.0
            self.select(self.index + 1)
        while self._scroll_accumulator <= -1.0:
            self._scroll_accumulator += 1.0
            self.select(self.index - 1)
        # Always claim the event: letting the scrolled window also scroll would
        # slide the selection off its anchor.
        return True

    def _update_hero(self) -> None:
        if not self.games:
            return
        game = self.games[self.index]
        self.hero_title.set_label(game.name)

        bits = [game.source_label or game.source]
        if game.developer:
            bits.append(game.developer)
        if game.categories:
            bits.append(", ".join(game.categories[:3]))
        if not game.installed:
            bits.append("nicht installiert")
        if game.play_seconds:
            bits.append(humanise_playtime(game.play_seconds))
        if game.last_played:
            bits.append("zuletzt " + time.strftime("%d.%m.%Y", time.localtime(game.last_played)))
        self.hero_subtitle.set_label("  ·  ".join(bits))

        self.hero_image.set_game(game)
        self.play_button.set_sensitive(bool(game.command))

        launcher = launcher_for(game.source)
        self.launcher_button.set_visible(launcher is not None)
        if launcher is not None:
            self.launcher_content.set_label(launcher[0])
            self.launcher_button.set_tooltip_text(
                f"{launcher[0]} öffnen, ohne das Spiel zu starten"
            )

        # The window fetches the banner for whatever is in the hero; doing it
        # for all several hundred games up front would be a lot of downloads
        # for images nobody looks at.
        self.emit("game-focused", game.game_id)

    def _emit_current(self, signal: str) -> None:
        if self.games:
            self.emit(signal, self.games[self.index].game_id)

    def _activate_current(self) -> None:
        self._emit_current("game-activated")

    # --- input --------------------------------------------------------------

    def _attach_gestures(self, card: GameCard, position: int) -> None:
        click = Gtk.GestureClick(button=1)
        click.connect("released", self._on_click, position)
        card.add_controller(click)

        secondary = Gtk.GestureClick(button=3)
        secondary.connect("pressed", self._on_secondary, card, position)
        card.add_controller(secondary)

    def _on_click(self, gesture, n_press, x, y, position):
        if position == self.index:
            self._activate_current()
        else:
            self.select(position)

    def _on_secondary(self, gesture, n_press, x, y, card, position):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.select(position)
        ok, bounds = card.compute_bounds(self)
        ox, oy = (bounds.origin.x, bounds.origin.y) if ok else (0, 0)
        self.emit("game-menu", self.games[position].game_id, ox + x, oy + y)

    def _on_key(self, controller, keyval, keycode, state) -> bool:
        if keyval in (Gdk.KEY_Left, Gdk.KEY_h):
            self.select(self.index - 1)
        elif keyval in (Gdk.KEY_Right, Gdk.KEY_l):
            self.select(self.index + 1)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._activate_current()
        elif keyval == Gdk.KEY_Home:
            self.select(0)
        elif keyval == Gdk.KEY_End:
            self.select(len(self.games) - 1)
        else:
            return False
        return True
