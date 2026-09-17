"""The ambient mode: a crossfading slideshow that takes over when idle."""

from __future__ import annotations

import logging
import random
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, GObject, Gtk, Pango  # noqa: E402

from ..ambient import candidates, ensure_image
from ..covers import new_session
from ..models import Game

log = logging.getLogger(__name__)

HOLD_SECONDS = 14          # how long one picture stays
FADE_MS = 1400
# How far the pointer must travel to count as someone reaching for the mouse.
# Appearing underneath a pointer that was already resting there delivers a
# motion event on its own, which would otherwise dismiss the slideshow in the
# same frame it started — and a mouse left sitting over the window is the
# normal case, not the exception.
WAKE_MOTION = 12


class AmbientView(Adw.Bin):
    """Covers the whole window; any input asks the window to put it away."""

    __gtype_name__ = "GamerackAmbientView"

    __gsignals__ = {
        "woken": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self.add_css_class("ambient")
        self.set_visible(False)

        self._games: list[Game] = []
        self._order: list[Game] = []
        self._timer = 0
        self._session = None
        self._generation = 0
        self._origin: tuple[float, float] | None = None

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               transition_duration=FADE_MS)
        self.frames = [Gtk.Picture(content_fit=Gtk.ContentFit.COVER),
                       Gtk.Picture(content_fit=Gtk.ContentFit.COVER)]
        for index, frame in enumerate(self.frames):
            frame.set_can_shrink(True)
            self.stack.add_named(frame, str(index))
        self._slot = 0

        self.caption = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                 halign=Gtk.Align.START, valign=Gtk.Align.END,
                                 margin_start=44, margin_bottom=40)
        self.caption.add_css_class("ambient-caption")

        overlay = Gtk.Overlay(child=self.stack)
        overlay.add_overlay(self.caption)
        self.set_child(overlay)

        # Any input at all dismisses it, which is why the controllers sit on
        # the overlay itself rather than on individual widgets.
        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_: self._wake())
        self.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        self.add_controller(motion)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda *_: self._wake() or True)
        self.add_controller(keys)
        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", lambda *_: self._wake() or True)
        self.add_controller(scroll)

    # --- library ------------------------------------------------------------

    def set_games(self, games) -> None:
        """Remember which games could be shown; only those with an image."""
        self._games = candidates(games)

    def available(self) -> int:
        return len(self._games)

    # --- running ------------------------------------------------------------

    def start(self) -> bool:
        """Begin the slideshow. False when there is nothing to show."""
        if not self._games:
            return False
        self._generation += 1
        self._order = list(self._games)
        random.shuffle(self._order)
        self._origin = None        # the first motion only records where we are
        self.set_visible(True)
        self.set_can_target(True)
        self.grab_focus()
        self._advance()
        if not self._timer:
            self._timer = GLib.timeout_add_seconds(HOLD_SECONDS, self._advance)
        return True

    def stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self._generation += 1
        self.set_visible(False)
        self.set_can_target(False)

    def _wake(self) -> None:
        self.emit("woken")

    def _on_motion(self, _controller, x: float, y: float) -> None:
        """Wake on a mouse that is being moved, not on one that is merely there."""
        if self._origin is None:
            self._origin = (x, y)
            return
        ox, oy = self._origin
        if abs(x - ox) + abs(y - oy) > WAKE_MOTION:
            self._wake()

    def _advance(self) -> bool:
        if not self._order:
            self._order = list(self._games)
            random.shuffle(self._order)
        game = self._order.pop()
        self._load(game, self._generation)
        return True

    def _load(self, game: Game, generation: int) -> None:
        """Fetch in a worker; a picture is not worth stalling the redraw for."""
        def work() -> None:
            if self._session is None:
                self._session = new_session()
            try:
                path = ensure_image(self._session, game)
            except Exception as error:      # never let the slideshow die
                log.info("Ambient-Bild fehlgeschlagen: %s", error)
                return
            if path is not None:
                GLib.idle_add(self._show, str(path), game.name, generation)

        threading.Thread(target=work, daemon=True, name="ambient").start()

    def _show(self, path: str, name: str, generation: int) -> bool:
        # A download that finishes after the mode ended, or after a restart,
        # must not flash a picture onto a library the user is looking at.
        if generation != self._generation or not self.get_visible():
            return False
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception:
            return False
        self._slot = 1 - self._slot
        self.frames[self._slot].set_paintable(texture)
        self.stack.set_visible_child_name(str(self._slot))
        self.caption.set_label(name)
        return False
