"""Shared UI building blocks: cover rendering and the game card."""

from __future__ import annotations

import hashlib
from collections import OrderedDict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, Gtk, Pango  # noqa: E402

from ..covers import BANNER_H, BANNER_W
from ..models import Game

COVER_RATIO = 2 / 3          # width / height
BANNER_RATIO = BANNER_W / BANNER_H
PLACEHOLDER_VARIANTS = 8


class TextureCache:
    """Keeps a bounded number of decoded covers in memory.

    Covers live on disk at 600x900; decoding all of them at once would cost
    hundreds of megabytes, so views only ask for what is on screen and the
    cache evicts the rest.
    """

    def __init__(self, limit: int = 120):
        self.limit = limit
        self._items: OrderedDict[tuple, Gdk.Texture] = OrderedDict()

    def get(self, path: str, width: int,
            ratio: float = COVER_RATIO) -> Gdk.Texture | None:
        if not path:
            return None
        bucket = max(64, round(width / 64) * 64)
        key = (path, bucket)
        if key in self._items:
            self._items.move_to_end(key)
            return self._items[key]
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, bucket, round(bucket / ratio), True
            )
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception:
            return None
        self._items[key] = texture
        while len(self._items) > self.limit:
            self._items.popitem(last=False)
        return texture

    def drop(self, path: str) -> None:
        for key in [k for k in self._items if k[0] == path]:
            del self._items[key]


TEXTURES = TextureCache()


def placeholder_class(name: str) -> str:
    digest = hashlib.md5(name.encode("utf-8")).digest()
    return f"ph-{digest[0] % PLACEHOLDER_VARIANTS}"


def initials(name: str) -> str:
    words = [w for w in name.replace(":", " ").split() if w[:1].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][:1] + words[1][:1]).upper()


class CoverLayout(Gtk.LayoutManager):
    """Forces the 2:3 shape regardless of what the child would ask for.

    Necessary because a GtkPicture reports its paintable's full pixel size as
    its natural size — a 600x900 cover would otherwise dictate the width of
    every column in the grid. GTK4 only honours custom measuring through a
    layout manager, not through a `do_measure` override on the widget.
    """

    __gtype_name__ = "GamerackCoverLayout"

    def do_get_request_mode(self, widget):
        # Constant size, not height-for-width: a cover's dimensions come from
        # its configured width alone. Negotiating height against the width it
        # happens to be offered makes horizontal containers (the list rows)
        # report contradictory minimum and natural heights.
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self, widget, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return widget.width, widget.width, -1, -1
        height = round(widget.width / COVER_RATIO)
        return height, height, -1, -1

    def do_allocate(self, widget, width, height, baseline):
        child = widget.get_first_child()
        if child is not None:
            child.allocate(width, height, baseline, None)


class FixedLayout(Gtk.LayoutManager):
    """Reports exactly `fixed_width` x `fixed_height`, whatever the child wants.

    Same reason as CoverLayout: a GtkPicture asks for its paintable's full pixel
    size, so a 600x900 image dropped into a grid of thumbnails would be drawn at
    600x900. A size request would only set a floor, not a ceiling.
    """

    __gtype_name__ = "GamerackFixedLayout"

    def do_get_request_mode(self, widget):
        return Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self, widget, orientation, for_size):
        size = (widget.fixed_width if orientation == Gtk.Orientation.HORIZONTAL
                else widget.fixed_height)
        return size, size, -1, -1

    def do_allocate(self, widget, width, height, baseline):
        child = widget.get_first_child()
        if child is not None:
            child.allocate(width, height, baseline, None)


class Thumbnail(Adw.Bin):
    """One image at an exact size, cropped to fill."""

    __gtype_name__ = "GamerackThumbnail"

    def __init__(self, texture: Gdk.Texture, width: int, height: int):
        super().__init__()
        self.fixed_width = width
        self.fixed_height = height
        self.set_layout_manager(FixedLayout())
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.add_css_class("cover")

        picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        picture.set_paintable(texture)
        self.set_child(picture)


class Cover(Adw.Bin):
    """A game cover at a fixed 2:3 ratio, with a generated fallback.

    The size is reported by `do_measure` rather than left to the child: a
    GtkPicture reports its paintable's full 600x900 as its natural size, which
    would otherwise blow up every column of the grid.
    """

    __gtype_name__ = "GamerackCover"

    def __init__(self, game: Game, width: int = 200):
        super().__init__()
        self.game = game
        self.width = width
        self.add_css_class("cover")
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.set_layout_manager(CoverLayout())
        self._loaded = False

        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        self.picture.set_can_shrink(True)

        self.fallback = Gtk.Label(label=initials(game.name))
        self.fallback.add_css_class("cover-initials")

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               transition_duration=220)
        self.stack.add_named(self.fallback, "fallback")
        self.stack.add_named(self.picture, "picture")
        self.stack.set_visible_child_name("fallback")
        self.set_child(self.stack)

        self._ph_class = placeholder_class(game.name)
        self.add_css_class(self._ph_class)
        self.set_size(width)

    def set_size(self, width: int) -> None:
        self.width = width
        self.queue_resize()

    def load(self) -> None:
        """Decode the cover if we have one. Cheap to call repeatedly."""
        if self._loaded or not self.game.cover_path:
            return
        texture = TEXTURES.get(self.game.cover_path, self.width * 2)
        if texture is None:
            return
        self.picture.set_paintable(texture)
        self.stack.set_visible_child_name("picture")
        self.remove_css_class(self._ph_class)
        self._loaded = True

    def unload(self) -> None:
        """Release the texture; the fallback takes over until we scroll back."""
        if not self._loaded:
            return
        self.picture.set_paintable(None)
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_visible_child_name("fallback")
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.add_css_class(self._ph_class)
        self._loaded = False

    def refresh(self) -> None:
        self._loaded = False
        self.load()


class Banner(Adw.Bin):
    """Wide artwork for the hero and the detail page.

    Falls back to the cover when no banner has been fetched yet: a portrait
    poster zoomed to fill a wide frame is a poor image but a fine backdrop, and
    it beats an empty rectangle while the real banner is still downloading.
    """

    __gtype_name__ = "GamerackBanner"

    def __init__(self, game: Game | None = None, height: int = 260):
        super().__init__()
        self.game = game
        self.add_css_class("banner")
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        self.picture.set_can_shrink(True)
        self.set_child(self.picture)
        self.set_size_request(-1, height)
        self._ph_class = ""
        if game is not None:
            self.set_game(game)

    def set_game(self, game: Game) -> None:
        if self._ph_class:
            self.remove_css_class(self._ph_class)
        self.game = game
        self._ph_class = placeholder_class(game.name)
        self.add_css_class(self._ph_class)
        self.refresh()

    def refresh(self) -> None:
        if self.game is None:
            return
        width = max(self.get_width(), 900)
        texture = None
        if self.game.banner_path:
            texture = TEXTURES.get(self.game.banner_path, width, BANNER_RATIO)
        if texture is None and self.game.cover_path:
            texture = TEXTURES.get(self.game.cover_path, 600)
        self.picture.set_paintable(texture)
        if texture is None:
            self.add_css_class(self._ph_class)
        else:
            self.remove_css_class(self._ph_class)


class GameCard(Gtk.Box):
    """Cover plus title — the tile used by the grid and the showcase strip."""

    def __init__(self, game: Game, width: int = 200, show_title: bool = True,
                 on_play=None, on_info=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.game = game
        self.add_css_class("game-card")
        self.set_overflow(Gtk.Overflow.HIDDEN)

        self.cover = Cover(game, width)
        if on_play is None and on_info is None:
            self.append(self.cover)
        else:
            self.append(self._with_hover_actions(on_play, on_info))

        # An ellipsizing label reports its full text as its natural width unless
        # max-width-chars caps it — without the cap a single long game name
        # widens every column in the homogeneous grid.
        self.title = Gtk.Label(label=game.name, xalign=0)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.title.set_max_width_chars(10)
        self.title.set_width_chars(6)
        self.title.add_css_class("game-title")
        if show_title:
            self.append(self.title)

        self.badge = Gtk.Label(label="")
        self.badge.add_css_class("state-badge")
        self.badge.set_visible(False)

        self.update()

    def _with_hover_actions(self, on_play, on_info) -> Gtk.Widget:
        """Put a play and an info button over the cover, shown while hovered."""
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                          halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                          hexpand=True, vexpand=True)

        for icon, tooltip, callback in (
            ("media-playback-start-symbolic", "Spielen", on_play),
            ("dialog-information-symbolic", "Großansicht", on_info),
        ):
            if callback is None:
                continue
            button = Gtk.Button(icon_name=icon, tooltip_text=tooltip)
            button.add_css_class("circular")
            button.add_css_class("osd")
            button.add_css_class("card-action")
            button.connect("clicked", lambda _b, cb=callback: cb(self.game))
            buttons.append(button)

        # Faded with a CSS class rather than wrapped in a GtkRevealer: an
        # overlay child set to fill is allocated the whole cover even when the
        # revealer shows nothing, so the revealer's own background would darken
        # every cover in the grid permanently.
        self.actions = Gtk.Box(halign=Gtk.Align.FILL, valign=Gtk.Align.FILL,
                               hexpand=True, vexpand=True)
        self.actions.append(buttons)
        self.actions.add_css_class("card-actions")
        self.actions.set_can_target(False)

        overlay = Gtk.Overlay(child=self.cover)
        overlay.add_overlay(self.actions)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self.set_actions_shown(True))
        motion.connect("leave", lambda *_: self.set_actions_shown(False))
        self.add_controller(motion)
        return overlay

    def set_actions_shown(self, shown: bool) -> None:
        if shown:
            self.actions.add_css_class("shown")
        else:
            self.actions.remove_css_class("shown")
        # Invisible buttons must not swallow the click that opens the game.
        self.actions.set_can_target(shown)

    def update(self) -> None:
        self.title.set_label(self.game.name)
        self.set_tooltip_text(
            self.game.name
            if self.game.installed
            else f"{self.game.name} — nicht installiert"
        )
        if self.game.installed:
            self.remove_css_class("not-installed")
        else:
            self.add_css_class("not-installed")

    def set_width(self, width: int) -> None:
        self.cover.set_size(width)
        self.set_size_request(width, -1)


class LazyCovers:
    """Loads covers for the cards currently on screen and frees the rest.

    Views register their cards, then call `update()` whenever the viewport
    moves. Cards well outside the visible area are unloaded so a library of a
    few hundred games stays light.
    """

    def __init__(self, scroller: Gtk.ScrolledWindow, margin: int = 600):
        self.scroller = scroller
        self.margin = margin
        self.cards: list[GameCard] = []
        self._queued = False

        for adjustment in (scroller.get_vadjustment(), scroller.get_hadjustment()):
            if adjustment is not None:
                adjustment.connect("value-changed", lambda *_: self.schedule())
        scroller.connect("notify::visible", lambda *_: self.schedule())

    def set_cards(self, cards: list[GameCard]) -> None:
        self.cards = cards
        self.schedule()

    def schedule(self) -> None:
        if self._queued:
            return
        self._queued = True
        from gi.repository import GLib
        GLib.timeout_add(40, self._run)

    def _run(self) -> bool:
        self._queued = False
        if not self.cards:
            return False

        # Bounds are taken relative to the scrolled window, so they already
        # account for the current scroll offset: anything inside
        # 0..width/height (plus a margin) is on or near the screen.
        width = self.scroller.get_width()
        height = self.scroller.get_height()
        if width <= 0 or height <= 0:
            for card in self.cards:
                card.cover.load()
            return False

        for card in self.cards:
            ok, bounds = card.compute_bounds(self.scroller)
            if not ok:
                card.cover.load()
                continue
            visible = (
                bounds.origin.y + bounds.size.height >= -self.margin
                and bounds.origin.y <= height + self.margin
                and bounds.origin.x + bounds.size.width >= -self.margin
                and bounds.origin.x <= width + self.margin
            )
            if visible:
                card.cover.load()
            else:
                card.cover.unload()
        return False
