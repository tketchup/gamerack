"""The main window: header, search, view switching and all window actions."""

from __future__ import annotations

import logging
import subprocess
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from .. import __version__
from ..covers import CoverFetcher
from ..gamepad import Gamepads
from ..history import History
from ..launchers import launcher_for
from ..metadata import MetadataFetcher
from ..models import Game, Library
from ..scanner import run_scan
from .ambient import AmbientView
from .artwork_picker import ArtworkPickerDialog
from .detail_page import GameDetailPage
from .details import GameDetailsDialog
from .filter_dialog import FilterDialog, filters_active
from .grid_view import GridView
from .list_view import ListView
from .preferences import PreferencesDialog
from .showcase_view import ShowcaseView
from .stats_page import StatsPage

log = logging.getLogger(__name__)

COVER_SIZES = [("Klein", "150"), ("Mittel", "200"), ("Groß", "260")]

SORTS = {
    "name": "Name",
    "recent": "Zuletzt gespielt",
    "added": "Zuletzt hinzugefügt",
    "playtime": "Spielzeit",
    "backlog": "Backlog-Score",
}

# The source filters, in menu order. "other" collects Flatpak, the application
# menu and anything added by hand.
BUCKETS = [("steam", "Steam"), ("heroic", "Heroic"), ("lutris", "Lutris"),
           ("other", "Sonstige")]

# How far into the window the pointer may reach before the console mode brings
# its header bar back, and how far it must travel down again to send it away.
# The gap between the two keeps the bar from flickering along the boundary.
BAR_REVEAL_EDGE = 40
BAR_HIDE_BELOW = 150


class MainWindow(Adw.ApplicationWindow):
    __gtype_name__ = "GamerackWindow"

    def __init__(self, application, library: Library, settings):
        super().__init__(application=application, title="Gamerack")
        self.library = library
        self.settings = settings
        self.set_default_size(1140, 780)
        self.set_size_request(360, 400)

        self.covers = CoverFetcher(settings, self._on_cover_ready)
        self.metadata = MetadataFetcher(settings, self._on_metadata_ready)
        self._scanning = False
        self.console = False

        self._build_ui()
        self._build_actions()
        self.refresh()

        self.pads = Gamepads(self._on_pad) if settings["gamepad"] else None

        if settings["scan_on_start"]:
            GLib.timeout_add(400, self._start_scan_idle)

    # --- construction -------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_view = GridView(self.settings["cover_size"])
        self.showcase_view = ShowcaseView()
        self.list_view = ListView()

        for view in (self.grid_view, self.showcase_view, self.list_view):
            view.connect("game-activated", self._on_game_activated)
            view.connect("game-menu", self._on_game_menu)
            view.connect("game-details", lambda _v, gid: self.show_detail_page(gid))
        for view in (self.showcase_view, self.list_view):
            view.connect("game-edit", lambda _v, gid: self._show_edit(gid))
            view.connect("game-launcher", lambda _v, gid: self._open_launcher(gid))
        # Banners are fetched for the game in the hero, not for the whole
        # library: nobody looks at three hundred of them.
        self.showcase_view.connect(
            "game-focused", lambda _v, gid: self._request_banner(gid)
        )

        self.views = {
            "grid": self.grid_view,
            "showcase": self.showcase_view,
            "list": self.list_view,
        }
        self._games: list[Game] = []
        self._stale: set[str] = set()

        self.view_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                                    transition_duration=160)
        for name, view in self.views.items():
            self.view_stack.add_named(view, name)
        self.view_stack.set_visible_child_name(self.settings["view"])

        self.title = Adw.WindowTitle(title="Alle Spiele", subtitle="")

        add_button = Gtk.Button(icon_name="list-add-symbolic",
                                tooltip_text="Spiel von Hand hinzufügen")
        add_button.connect("clicked", lambda *_: self._add_game_dialog())

        self.search_button = Gtk.ToggleButton(icon_name="system-search-symbolic",
                                              tooltip_text="Suchen (Strg+F)")

        self.console_button = Gtk.ToggleButton(
            icon_name="view-fullscreen-symbolic",
            tooltip_text="Konsolenmodus: Schaufenster im Vollbild (F11)",
        )
        self.console_button.connect("toggled",
                                    lambda button: self.set_console(button.get_active()))

        stats_button = Gtk.Button(icon_name="histogram-symbolic",
                                  tooltip_text="Statistik")
        stats_button.connect("clicked", lambda *_: self.show_stats())

        self.filter_button = Gtk.Button(icon_name="funnel-symbolic")
        self.filter_button.connect("clicked", lambda *_: self._show_filters())

        layout_button = Gtk.MenuButton(icon_name="view-grid-symbolic",
                                       tooltip_text="Ansicht",
                                       menu_model=self._layout_menu())
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic",
                                     tooltip_text="Hauptmenü",
                                     menu_model=self._main_menu())

        self.spinner = Adw.Spinner()
        self.spinner.set_visible(False)

        header = Adw.HeaderBar(title_widget=self.title)
        header.pack_start(add_button)
        header.pack_start(self.spinner)
        header.pack_end(menu_button)
        header.pack_end(layout_button)
        header.pack_end(stats_button)
        header.pack_end(self.filter_button)
        header.pack_end(self.search_button)
        header.pack_end(self.console_button)

        self.search_entry = Gtk.SearchEntry(placeholder_text="Spiele durchsuchen",
                                            hexpand=True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self._search_timeout = 0
        self.search_bar = Gtk.SearchBar(child=self.search_entry,
                                        show_close_button=False)
        self.search_button.bind_property(
            "active", self.search_bar, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.toolbar = Adw.ToolbarView()
        self.toolbar.add_top_bar(header)
        self.toolbar.add_top_bar(self.search_bar)
        self.toolbar.set_content(self.view_stack)

        # The search bar listens on the library page only, so typing on the
        # detail page does not pop it open behind you.
        self.search_bar.set_key_capture_widget(self.toolbar)

        self.library_page = Adw.NavigationPage(title="Alle Spiele", tag="library",
                                               child=self.toolbar)
        self.detail_page = GameDetailPage(self.settings)
        self.detail_page.connect("play-requested", lambda _p, gid: self._launch(gid))
        self.detail_page.connect("edit-requested", lambda _p, gid: self._show_edit(gid))
        self.detail_page.connect("hide-requested", lambda _p, gid: self._toggle_hidden(gid))
        self.detail_page.connect("launcher-requested", lambda _p, gid: self._open_launcher(gid))
        self.detail_page.connect("banner-requested",
                                 lambda _p, gid: self._pick_artwork(gid, "banner"))

        # A library built without a log (tests, scripts) still gets a page;
        # an empty History simply has nothing to report.
        if self.library.history is None:
            self.library.history = History()
        self.stats_page = StatsPage(self.library, self.library.history)
        self.stats_page.connect("open-requested",
                                lambda _p, gid: self.show_detail_page(gid))

        self.nav = Adw.NavigationView()
        self.nav.add(self.library_page)

        self.toasts = Adw.ToastOverlay(child=self.nav)

        # Over everything, header included: a slideshow with a toolbar across
        # it is not a slideshow.
        self.ambient = AmbientView()
        self.ambient.connect("woken", lambda *_: self._stop_ambient())
        root = Gtk.Overlay(child=self.toasts)
        root.add_overlay(self.ambient)
        self.set_content(root)

        self._last_input = time.monotonic()
        GLib.timeout_add_seconds(2, self._check_idle)

        self.context_menu = Gtk.PopoverMenu()
        self.context_menu.set_has_arrow(False)
        self.context_menu.set_halign(Gtk.Align.START)
        self.context_menu.set_parent(self.view_stack)

        # Bubble phase, so the navigation view gets first refusal on Escape and
        # we only see the ones it did not use to go back a page.
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        # A second one in capture phase, for the idle clock alone: a keystroke
        # a child swallows is still someone sitting there.
        watch = Gtk.EventControllerKey()
        watch.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        watch.connect("key-pressed", lambda *_: (self._note_activity(), False)[1])
        self.add_controller(watch)

        # Capture phase, so the pointer is tracked wherever it is over the
        # window and not only where no child happens to be handling motion.
        motion = Gtk.EventControllerMotion()
        motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        motion.connect("motion", self._on_pointer)
        motion.connect("leave", lambda *_: self.console and self._reveal_bars(False))
        self.add_controller(motion)

        self.connect("notify::fullscreened", self._on_fullscreen_changed)

    def _layout_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("Raster", "win.view::grid")
        section.append("Schaufenster", "win.view::showcase")
        section.append("Liste", "win.view::list")
        menu.append_section("Ansicht", section)

        size_section = Gio.Menu()
        for label, value in COVER_SIZES:
            size_section.append(label, f"win.cover-size::{value}")
        menu.append_section("Cover-Größe", size_section)

        # Only the switch that gets flipped constantly stays here. Sources,
        # sorting, backlog and hidden games moved into the filter dialog,
        # where each one has room for a label that explains it.
        filter_section = Gio.Menu()
        filter_section.append("Nur installierte", "win.only-installed")
        filter_section.append("Filter…", "win.filters")
        menu.append_section(None, filter_section)
        return menu

    def _main_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("Neu suchen", "win.rescan")
        section.append("Fehlende Cover laden", "win.fetch-covers")
        section.append("Metadaten nachladen", "win.fetch-metadata")
        menu.append_section(None, section)

        section = Gio.Menu()
        section.append("Statistik", "win.stats")
        section.append("Konsolenmodus", "win.console")
        menu.append_section(None, section)

        section = Gio.Menu()
        section.append("Einstellungen", "win.preferences")
        section.append("Tastenkürzel", "win.shortcuts")
        section.append("Über Gamerack", "win.about")
        menu.append_section(None, section)
        return menu

    def _context_menu(self, game: Game) -> Gio.Menu:
        """Built per game: the launcher entry only appears when there is one."""
        menu = Gio.Menu()
        menu.append("Spielen", "win.launch-selected")
        menu.append("Details…", "win.details-selected")
        menu.append("Bearbeiten…", "win.edit-selected")

        launcher = launcher_for(game.source)
        if launcher is not None:
            menu.append(f"{launcher[0]} öffnen", "win.launcher-selected")

        menu.append("Einblenden" if game.hidden else "Ausblenden",
                    "win.hide-selected")
        return menu

    # --- actions ------------------------------------------------------------

    def _build_actions(self) -> None:
        simple = {
            "rescan": lambda *_: self.start_scan(),
            "fetch-covers": lambda *_: self._fetch_missing_covers(),
            "fetch-metadata": lambda *_: self._fetch_metadata(),
            "preferences": lambda *_: self._show_preferences(),
            "about": lambda *_: self._show_about(),
            "shortcuts": lambda *_: self._show_shortcuts(),
            "stats": lambda *_: self.show_stats(),
            "filters": lambda *_: self._show_filters(),
            "launch-selected": lambda *_: self._launch(self._menu_target),
            "details-selected": lambda *_: self.show_detail_page(self._menu_target),
            "edit-selected": lambda *_: self._show_edit(self._menu_target),
            "launcher-selected": lambda *_: self._open_launcher(self._menu_target),
            "hide-selected": lambda *_: self._toggle_hidden(self._menu_target),
        }
        for name, callback in simple.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        view = Gio.SimpleAction.new_stateful(
            "view", GLib.VariantType.new("s"),
            GLib.Variant.new_string(self.settings["view"]),
        )
        view.connect("activate", self._on_view_action)
        self.add_action(view)

        cover_size = Gio.SimpleAction.new_stateful(
            "cover-size", GLib.VariantType.new("s"),
            GLib.Variant.new_string(str(self.settings["cover_size"])),
        )
        cover_size.connect("activate", self._on_cover_size_action)
        self.add_action(cover_size)

        action = Gio.SimpleAction.new_stateful(
            "only-installed", None,
            GLib.Variant.new_boolean(self.settings["only_installed"]),
        )
        action.connect("activate", self._on_toggle_action, "only_installed")
        self.add_action(action)

        console = Gio.SimpleAction.new_stateful(
            "console", None, GLib.Variant.new_boolean(False)
        )
        console.connect("activate", lambda *_: self.set_console(not self.console))
        self.add_action(console)

        self._menu_target = ""

    def _on_view_action(self, action, parameter) -> None:
        name = parameter.get_string()
        action.set_state(parameter)
        self.settings["view"] = name
        if name in self._stale:
            self._stale.discard(name)
            self.views[name].set_games(self._games)
        self.view_stack.set_visible_child_name(name)
        if name == "showcase":
            self.showcase_view.grab_focus()

    def _on_cover_size_action(self, action, parameter) -> None:
        action.set_state(parameter)
        width = int(parameter.get_string())
        self.settings["cover_size"] = width
        self.grid_view.set_cover_width(width)

    def _on_toggle_action(self, action, _parameter, key: str) -> None:
        new_state = not action.get_state().get_boolean()
        action.set_state(GLib.Variant.new_boolean(new_state))
        self.settings[key] = new_state
        self.refresh()

    # --- ambient mode -------------------------------------------------------

    def _note_activity(self) -> None:
        self._last_input = time.monotonic()

    def _check_idle(self) -> bool:
        """Start the slideshow once the showcase has sat still long enough."""
        if not self.settings["ambient"] or self.ambient.get_visible():
            return True
        if self.view_stack.get_visible_child_name() != "showcase":
            return True
        # Only on the library page: the detail page is something you opened on
        # purpose and are presumably reading.
        if self.nav.get_visible_page() is not self.library_page:
            return True
        if time.monotonic() - self._last_input < self.settings["ambient_delay"]:
            return True
        self.ambient.set_games(self._games)
        if not self.ambient.start():
            log.info("Ambient-Modus: kein Spiel mit 16:9-Bild verfügbar")
            self._note_activity()      # do not retry every two seconds
        return True

    def _stop_ambient(self) -> None:
        self.ambient.stop()
        self._note_activity()
        if self.view_stack.get_visible_child_name() == "showcase":
            self.showcase_view.grab_focus()

    # --- console mode -------------------------------------------------------

    def set_console(self, on: bool) -> None:
        """Fullscreen showcase, meant to be driven from an armchair."""
        if on == self.console:
            return
        self.console = on

        view = self.lookup_action("view")
        if on:
            # Remember what the user actually prefers: the console mode forces
            # the showcase, and leaving it must not have quietly rewritten the
            # view Gamerack starts up in.
            self._view_before_console = self.view_stack.get_visible_child_name()
            view.activate(GLib.Variant.new_string("showcase"))
            self.add_css_class("console")
            self._extend_under_bars(True)
            self._reveal_bars(False)
            self.fullscreen()
            self.present()
            self.showcase_view.grab_focus()
        else:
            self.remove_css_class("console")
            self._extend_under_bars(False)
            self._reveal_bars(True)
            self.unfullscreen()
            # Only put the old view back if they did not pick a different one
            # themselves while the console mode was up.
            previous = getattr(self, "_view_before_console", None)
            if previous and self.view_stack.get_visible_child_name() == "showcase":
                view.activate(GLib.Variant.new_string(previous))

        self.console_button.set_active(on)
        action = self.lookup_action("console")
        if action is not None:
            action.set_state(GLib.Variant.new_boolean(on))

    def _bars(self):
        return (self.toolbar, self.detail_page.toolbar)

    def _extend_under_bars(self, extend: bool) -> None:
        """Let the content run to the top edge, so a hidden bar leaves no gap."""
        # Raised while it floats over the artwork: an extended toolbar view
        # draws its bars transparent, and white-on-banner is unreadable.
        style = Adw.ToolbarStyle.RAISED if extend else Adw.ToolbarStyle.FLAT
        for bar in self._bars():
            bar.set_extend_content_to_top_edge(extend)
            bar.set_top_bar_style(style)

    def _reveal_bars(self, revealed: bool) -> None:
        for bar in self._bars():
            bar.set_reveal_top_bars(revealed)

    def _on_pointer(self, _controller, _x, y: float) -> None:
        """In console mode the header hides until the mouse reaches for it."""
        self._note_activity()
        if not self.console:
            return
        if y <= BAR_REVEAL_EDGE:
            self._reveal_bars(True)
        elif y > BAR_HIDE_BELOW:
            self._reveal_bars(False)

    def _on_fullscreen_changed(self, *_args) -> None:
        # Follow the window's real state in both directions. Fullscreen reached
        # any other way — the window manager's own shortcut, a title bar button —
        # is the console mode too, otherwise the pad would sit there dead in a
        # fullscreen window that merely looks right.
        self.set_console(self.is_fullscreen())

    def _on_key(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval == Gdk.KEY_Escape and self.console:
            self.set_console(False)
            return True
        return False

    # --- gamepad ------------------------------------------------------------

    def _on_pad(self, action: str) -> None:
        """One button or direction from any connected pad."""
        self._note_activity()
        if self.ambient.get_visible():
            # The button that wakes it does nothing else, same as a keypress
            # against a screensaver.
            self._stop_ambient()
            return
        if action in ("start", "guide"):
            self.set_console(not self.console)
            return
        if not self.console:
            return

        self.set_focus_visible(True)
        on_library = self.nav.get_visible_page() is self.library_page
        in_showcase = (on_library
                       and self.view_stack.get_visible_child_name() == "showcase")

        if action == "b":
            if not on_library:
                self.nav.pop()
            else:
                self.set_console(False)
            return

        if in_showcase:
            self._pad_showcase(action)
        else:
            self._pad_focus(action)

    def _pad_showcase(self, action: str) -> None:
        view = self.showcase_view
        if action == "left":
            view.select(view.index - 1)
        elif action == "right":
            view.select(view.index + 1)
        elif action == "a":
            view._activate_current()
        elif action in ("y", "up"):
            view._emit_current("game-details")
        elif action == "x":
            view._emit_current("game-edit")

    def _pad_focus(self, action: str) -> None:
        """Everywhere else the pad simply drives GTK's own focus handling."""
        directions = {
            "left": Gtk.DirectionType.LEFT,
            "right": Gtk.DirectionType.RIGHT,
            "up": Gtk.DirectionType.UP,
            "down": Gtk.DirectionType.DOWN,
        }
        if action in directions:
            self.child_focus(directions[action])
        elif action == "a":
            target = self.get_focus()
            if target is not None:
                target.activate()

    # --- library presentation ----------------------------------------------

    def visible_games(self) -> list[Game]:
        query = self.search_entry.get_text().strip().lower()
        games = self.library.visible(include_hidden=self.settings["show_hidden"])

        games = [g for g in games if self.settings.bucket_shown(g.bucket)]
        if self.settings["only_installed"]:
            games = [g for g in games if g.installed]
        if self.settings["backlog_only"]:
            floor = self.settings["backlog_min"]
            games = [g for g in games
                     if g.backlog_score is not None and g.backlog_score >= floor]
        if query:
            games = [
                g for g in games
                if query in g.name.lower()
                or query in (g.developer or "").lower()
                or query in (g.source_label or "").lower()
            ]

        sort = self.settings["sort"]
        if sort == "recent":
            games.sort(key=lambda g: (-g.last_played, g.sort_name))
        elif sort == "added":
            games.sort(key=lambda g: (-g.added, g.sort_name))
        elif sort == "playtime":
            games.sort(key=lambda g: (-g.play_seconds, g.sort_name))
        elif sort == "backlog":
            # Games outside a launcher have no score; they go last rather than
            # disappearing, so switching the sort never hides anything.
            games.sort(key=lambda g: (-(g.backlog_score or -1), g.sort_name))
        else:
            games.sort(key=lambda g: g.sort_name)
        return games

    def _on_search_changed(self, _entry) -> None:
        # Coalesce keystrokes: rebuilding the view is the expensive part.
        if self._search_timeout:
            GLib.source_remove(self._search_timeout)

        def apply():
            self._search_timeout = 0
            self.refresh()
            return False

        self._search_timeout = GLib.timeout_add(160, apply)

    def refresh(self) -> None:
        """Rebuild the visible view now; the others when they are switched to.

        Populating a view means creating a widget tree per game, so doing all
        three on every keystroke in the search entry is far too slow for a
        library of a few hundred titles.
        """
        games = self.visible_games()
        self._games = games
        current = self.view_stack.get_visible_child_name() or "grid"
        self._stale = {name for name in self.views if name != current}
        self.views[current].set_games(games)

        total = len(self.library.visible(include_hidden=True))
        shown = len(games)
        subtitle = f"{shown} von {total} Spielen" if shown != total else f"{shown} Spiele"
        self.title.set_subtitle(subtitle)
        self._update_filter_button()

        # Always queue: local artwork is resolved even when network fetching
        # is off, and the fetcher skips anything that already has a cover.
        self.covers.request_many(games)
        self.metadata.request_many(games)

    # --- scanning -----------------------------------------------------------

    def _start_scan_idle(self) -> bool:
        self.start_scan(quiet=True)
        return False

    def start_scan(self, quiet: bool = False) -> None:
        if self._scanning:
            return
        self._scanning = True
        self.spinner.set_visible(True)

        def work():
            try:
                scanned = run_scan(self.settings)
            except Exception:
                log.exception("Suchlauf fehlgeschlagen")
                scanned = []
            GLib.idle_add(self._finish_scan, scanned, quiet)

        threading.Thread(target=work, daemon=True, name="scan").start()

    def _finish_scan(self, scanned: list[Game], quiet: bool) -> bool:
        new, _updated = self.library.merge(scanned)
        self.library.save()
        self._scanning = False
        self.spinner.set_visible(False)
        self.refresh()

        if new:
            self.toasts.add_toast(Adw.Toast(
                title=f"{len(new)} neue Spiele gefunden", timeout=4
            ))
        elif not quiet:
            self.toasts.add_toast(Adw.Toast(title="Keine neuen Spiele", timeout=3))
        return False

    # --- covers -------------------------------------------------------------

    def _on_cover_ready(self, game: Game, kind: str = "cover") -> None:
        """Called from a cover worker thread."""
        GLib.idle_add(self._apply_cover, game, kind)

    def _apply_cover(self, game: Game, kind: str = "cover") -> bool:
        if kind == "banner":
            self.showcase_view.refresh_cover(game)
            if self.detail_page.game is game:
                self.detail_page.refresh_artwork()
        else:
            self.grid_view.refresh_cover(game)
            self.showcase_view.refresh_cover(game)
            self.list_view.refresh_cover(game)
            if self.detail_page.game is game:
                self.detail_page.refresh_artwork()
        self._save_soon()
        return False

    def _on_metadata_ready(self, game: Game) -> None:
        """Called from the metadata worker thread."""
        GLib.idle_add(self._apply_metadata, game)

    def _apply_metadata(self, game: Game) -> bool:
        self.list_view.refresh_cover(game)
        self.showcase_view.refresh_game(game)
        if self.detail_page.game is game:
            self.detail_page.set_game(game)
        self._save_soon()
        return False

    def _request_banner(self, game_id: str) -> None:
        game = self.library.games.get(game_id)
        if game is not None:
            self.covers.request(game, "banner")
            self.metadata.request(game, urgent=True)

    def _save_soon(self) -> None:
        if getattr(self, "_save_pending", False):
            return
        self._save_pending = True

        def flush():
            self._save_pending = False
            self.library.save()
            return False

        GLib.timeout_add_seconds(3, flush)

    def _fetch_missing_covers(self) -> None:
        missing = [g for g in self.library.visible(include_hidden=True)
                   if not g.cover_path]
        self.covers.request_many(missing)
        self.toasts.add_toast(Adw.Toast(
            title=f"Suche Cover für {len(missing)} Spiele" if missing
            else "Alle Spiele haben ein Cover",
            timeout=3,
        ))

    def _fetch_metadata(self) -> None:
        if not self.settings["fetch_metadata"]:
            self.toasts.add_toast(Adw.Toast(
                title="Metadaten sind in den Einstellungen abgeschaltet"
            ))
            return
        games = [g for g in self.library.visible(include_hidden=True)
                 if not g.categories or not g.release_date]
        self.metadata.request_many(games, force=True)
        self.toasts.add_toast(Adw.Toast(
            title=f"Metadaten für {len(games)} Spiele werden geladen" if games
            else "Alle Spiele haben schon Metadaten",
            timeout=3,
        ))

    # --- game interaction ---------------------------------------------------

    def _on_game_activated(self, _view, game_id: str) -> None:
        self._launch(game_id)

    def _on_game_menu(self, view, game_id: str, x: float, y: float) -> None:
        self._menu_target = game_id
        game = self.library.games.get(game_id)
        if game is None:
            return
        self.context_menu.set_menu_model(self._context_menu(game))
        ok, bounds = view.compute_bounds(self.view_stack)
        ox, oy = (bounds.origin.x, bounds.origin.y) if ok else (0, 0)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(ox + x), int(oy + y), 1, 1
        self.context_menu.set_pointing_to(rect)
        self.context_menu.popup()

    def _launch(self, game_id: str) -> None:
        self._stop_ambient()
        game = self.library.games.get(game_id)
        if game is None or not game.command:
            self.toasts.add_toast(Adw.Toast(title="Kein Startbefehl hinterlegt"))
            return
        try:
            subprocess.Popen(
                game.command,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError) as error:
            self.toasts.add_toast(Adw.Toast(title=f"Start fehlgeschlagen: {error}"))
            return

        game.last_played = time.time()
        game.play_count += 1
        if self.library.history is not None:
            self.library.history.launched(game.game_id, game.last_played)
        self.library.save()
        self.toasts.add_toast(Adw.Toast(title=f"„{game.name}“ wird gestartet", timeout=3))
        if self.settings["sort"] == "recent":
            GLib.timeout_add_seconds(1, lambda: (self.refresh(), False)[1])

    def show_stats(self) -> None:
        """Open the statistics page, rebuilt from the log each time."""
        self.stats_page.refresh()
        if self.nav.get_visible_page() is not self.stats_page:
            self.nav.push(self.stats_page)

    def show_detail_page(self, game_id: str) -> None:
        """Open the full-page view for one game."""
        game = self.library.games.get(game_id)
        if game is None:
            return
        self.detail_page.set_game(game)
        self.covers.request(game, "banner")
        self.metadata.request(game, urgent=True)
        if self.nav.get_visible_page() is not self.detail_page:
            self.nav.push(self.detail_page)
        if self.console:
            # Give the pad something to act on straight away.
            GLib.idle_add(self.detail_page.play_button.grab_focus)

    def _show_edit(self, game_id: str) -> None:
        game = self.library.games.get(game_id)
        if game is None:
            return
        dialog = GameDetailsDialog(game, self.library, self.settings)
        dialog.connect("saved", self._on_game_edited)
        dialog.connect("artwork-changed", self._on_game_edited)
        dialog.connect("removed", self._on_game_removed)
        dialog.present(self)

    def _on_game_edited(self, _dialog, game_id: str) -> None:
        self.refresh()
        game = self.library.games.get(game_id)
        if game is not None and self.detail_page.game is not None \
                and self.detail_page.game.game_id == game_id:
            self.detail_page.set_game(game)

    def _on_game_removed(self, _dialog, game_id: str) -> None:
        if self.nav.get_visible_page() is self.detail_page:
            self.nav.pop()
        self.refresh()

    def _pick_artwork(self, game_id: str, kind: str) -> None:
        game = self.library.games.get(game_id)
        if game is None:
            return
        picker = ArtworkPickerDialog(game, self.settings, kind)
        picker.connect("chosen", self._on_artwork_chosen)
        picker.present(self)

    def _on_artwork_chosen(self, _picker, game_id: str, kind: str) -> None:
        game = self.library.games.get(game_id)
        if game is None:
            return
        self.library.save()
        self._apply_cover(game, kind)

    def _open_launcher(self, game_id: str) -> None:
        game = self.library.games.get(game_id)
        if game is None:
            return
        launcher = launcher_for(game.source)
        if launcher is None:
            self.toasts.add_toast(Adw.Toast(title="Kein Launcher gefunden"))
            return
        label, command = launcher
        try:
            subprocess.Popen(
                command,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError) as error:
            self.toasts.add_toast(Adw.Toast(title=f"{label} startet nicht: {error}"))
            return
        self.toasts.add_toast(Adw.Toast(title=f"{label} wird geöffnet", timeout=3))

    def _toggle_hidden(self, game_id: str) -> None:
        game = self.library.games.get(game_id)
        if game is None:
            return
        game.set_override("hidden", not game.hidden)
        self.library.save()
        self.refresh()
        if self.detail_page.game is game:
            self.detail_page.set_game(game)
        toast = Adw.Toast(title=f"„{game.name}“ ausgeblendet" if game.hidden
                          else f"„{game.name}“ wieder sichtbar", timeout=4)
        toast.set_button_label("Rückgängig")
        toast.connect("button-clicked", lambda *_: self._toggle_hidden(game_id))
        self.toasts.add_toast(toast)

    def _add_game_dialog(self) -> None:
        game = Game(
            game_id=f"manual:{int(time.time() * 1000)}",
            source="manual",
            source_label="Manuell",
            name="Neues Spiel",
            command=[],
        )
        self.library.add(game)
        dialog = GameDetailsDialog(game, self.library, self.settings)
        dialog.connect("saved", self._on_game_edited)
        dialog.connect("artwork-changed", self._on_game_edited)
        dialog.connect("removed", self._on_game_removed)
        dialog.connect("closed", self._drop_unsaved, game.game_id)
        dialog.present(self)

    def _drop_unsaved(self, _dialog, game_id: str) -> None:
        game = self.library.games.get(game_id)
        if game is not None and not game.command and game.name == "Neues Spiel":
            self.library.remove(game_id)

    # --- dialogs ------------------------------------------------------------

    def _show_filters(self) -> None:
        dialog = FilterDialog(self.settings, BUCKETS, SORTS, self._filter_counts)
        dialog.connect("changed", lambda *_: self.refresh())
        dialog.present(self)

    def _filter_counts(self) -> tuple[int, int]:
        """How many games the current filters leave, and how many exist."""
        return len(self.visible_games()), len(self.library.visible(True))

    def _update_filter_button(self) -> None:
        """Mark the funnel while it is actually holding something back."""
        active = filters_active(self.settings, BUCKETS)
        if active:
            self.filter_button.add_css_class("accent")
        else:
            self.filter_button.remove_css_class("accent")
        self.filter_button.set_tooltip_text(
            "Filter — aktiv" if active else "Filter"
        )

    def _show_preferences(self) -> None:
        dialog = PreferencesDialog(self.settings, self.pads)
        dialog.connect("rescan-requested", lambda *_: self.start_scan())
        dialog.connect("covers-requested", lambda *_: self._fetch_missing_covers())
        dialog.present(self)

    def _show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name="Gamerack",
            application_icon="applications-games",
            version=__version__,
            developer_name="Von einer KI geschrieben",
            comments="Eine Spielebibliothek für Linux: findet Spiele in Steam, "
                     "Heroic, Lutris, Flatpak und im Anwendungsmenü und zeigt sie "
                     "als Raster, Schaufenster oder Liste.",
            license_type=Gtk.License.GPL_3_0,
        )
        about.add_credit_section("Cover-Bilder", ["SteamGridDB", "Valve Steam CDN"])
        about.present(self)

    def _show_shortcuts(self) -> None:
        rows = [
            ("Strg + F", "Suche öffnen"),
            ("Strg + R", "Neu suchen"),
            ("Strg + 1 / 2 / 3", "Raster / Schaufenster / Liste"),
            ("Strg + ,", "Einstellungen"),
            ("Klick, Enter", "Großansicht eines Spiels öffnen"),
            ("Zeigen, dann ▶", "Direkt starten, ohne Umweg"),
            ("Rechtsklick", "Menü für ein Spiel"),
            ("Esc", "Zurück zur Bibliothek, Konsolenmodus verlassen"),
            ("F11", "Konsolenmodus"),
            ("← / →, Enter", "Im Schaufenster blättern und starten"),
            ("Start am Controller", "Konsolenmodus öffnen und schließen"),
            ("A / B am Controller", "Spielen / zurück"),
            ("Y am Controller", "Großansicht"),
        ]
        group = Adw.PreferencesGroup()
        for keys, description in rows:
            group.add(Adw.ActionRow(title=description, subtitle=keys))

        page = Adw.PreferencesPage()
        page.add(group)

        dialog = Adw.Dialog()
        dialog.set_title("Tastenkürzel")
        dialog.set_content_width(420)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(page)
        dialog.set_child(toolbar)
        dialog.present(self)
