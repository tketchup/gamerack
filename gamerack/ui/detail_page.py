"""The full-page view for a single game, reached by clicking a cover."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk, Pango  # noqa: E402

from ..launchers import launcher_for
from ..models import Game, humanise_date, humanise_playtime
from .widgets import Banner

BANNER_HEIGHT = 300


class GameDetailPage(Adw.NavigationPage):
    """One reusable page; `set_game` swaps its contents before it is pushed."""

    __gtype_name__ = "GamerackDetailPage"

    __gsignals__ = {
        "play-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "edit-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "hide-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "launcher-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "banner-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__(title="Spiel", tag="detail")
        self.game: Game | None = None

        self.window_title = Adw.WindowTitle()
        header = Adw.HeaderBar(title_widget=self.window_title)
        header.add_css_class("flat")
        # The console toggle is meant to be reachable at all times, so this page
        # carries its own copy wired to the same window action.
        header.pack_end(Gtk.ToggleButton(
            icon_name="view-fullscreen-symbolic",
            tooltip_text="Konsolenmodus (F11)",
            action_name="win.console",
        ))

        self.toolbar = Adw.ToolbarView()
        self.toolbar.add_top_bar(header)
        self.toolbar.set_content(self._build_body())
        self.set_child(self.toolbar)

    # --- construction -------------------------------------------------------

    def _build_body(self) -> Gtk.Widget:
        self.banner = Banner(height=BANNER_HEIGHT)

        scrim = Gtk.Box()
        scrim.add_css_class("hero-scrim")

        self.hero_title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.hero_title.add_css_class("hero-title")
        self.hero_subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.hero_subtitle.add_css_class("hero-subtitle")

        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                         valign=Gtk.Align.END, hexpand=True)
        titles.add_css_class("hero-info")
        titles.append(self.hero_title)
        titles.append(self.hero_subtitle)

        change_banner = Gtk.Button(icon_name="document-edit-symbolic",
                                   tooltip_text="Banner suchen oder auswählen",
                                   halign=Gtk.Align.END, valign=Gtk.Align.START,
                                   margin_top=12, margin_end=12)
        change_banner.add_css_class("circular")
        change_banner.add_css_class("osd")
        change_banner.connect(
            "clicked", lambda *_: self._emit_for("banner-requested")
        )

        hero = Gtk.Overlay(child=self.banner)
        hero.add_overlay(scrim)
        hero.add_overlay(titles)
        hero.add_overlay(change_banner)
        hero.set_overflow(Gtk.Overflow.HIDDEN)

        self.play_button = Gtk.Button()
        self.play_button.set_child(
            Adw.ButtonContent(icon_name="media-playback-start-symbolic", label="Spielen")
        )
        self.play_button.add_css_class("suggested-action")
        self.play_button.add_css_class("pill")
        self.play_button.connect("clicked", lambda *_: self._emit_for("play-requested"))

        self.edit_button = Gtk.Button()
        self.edit_button.set_child(
            Adw.ButtonContent(icon_name="document-edit-symbolic", label="Bearbeiten")
        )
        self.edit_button.add_css_class("pill")
        self.edit_button.connect("clicked", lambda *_: self._emit_for("edit-requested"))

        self.hide_button = Gtk.Button()
        self.hide_content = Adw.ButtonContent(icon_name="view-conceal-symbolic",
                                              label="Ausblenden")
        self.hide_button.set_child(self.hide_content)
        self.hide_button.add_css_class("pill")
        self.hide_button.connect("clicked", lambda *_: self._emit_for("hide-requested"))

        self.launcher_button = Gtk.Button()
        self.launcher_content = Adw.ButtonContent(icon_name="external-link-symbolic",
                                                  label="Launcher")
        self.launcher_button.set_child(self.launcher_content)
        self.launcher_button.add_css_class("pill")
        self.launcher_button.connect("clicked", lambda *_: self._emit_for("launcher-requested"))

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                          halign=Gtk.Align.START)
        buttons.add_css_class("detail-buttons")
        for button in (self.play_button, self.edit_button, self.hide_button,
                       self.launcher_button):
            buttons.append(button)

        self.summary = Gtk.Label(xalign=0, wrap=True, yalign=0)
        self.summary.add_css_class("detail-summary")

        self.tags = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                halign=Gtk.Align.START, column_spacing=8,
                                row_spacing=8, max_children_per_line=8)

        self.facts = Adw.PreferencesGroup(title="Details")
        self.fact_rows: dict[str, Adw.ActionRow] = {}
        for key, title in (
            ("playtime", "Gesamtspielzeit"),
            ("last_played", "Zuletzt gespielt"),
            ("launches", "Gestartet"),
            ("developer", "Entwickler"),
            ("publisher", "Publisher"),
            ("release", "Erschienen"),
            ("source", "Quelle"),
            ("status", "Status"),
            ("install_dir", "Ordner"),
        ):
            row = Adw.ActionRow(title=title)
            row.add_css_class("property")
            row.set_subtitle_selectable(True)
            self.facts.add(row)
            self.fact_rows[key] = row

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                          margin_top=20, margin_bottom=30)
        content.append(buttons)
        content.append(self.tags)
        content.append(self.summary)
        content.append(self.facts)

        clamp = Adw.Clamp(maximum_size=820, tightening_threshold=640,
                          child=content, margin_start=18, margin_end=18)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.append(hero)
        page.append(clamp)

        return Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vexpand=True, child=page)

    def _emit_for(self, signal: str) -> None:
        if self.game is not None:
            self.emit(signal, self.game.game_id)

    # --- population ---------------------------------------------------------

    def set_game(self, game: Game) -> None:
        self.game = game
        self.set_title(game.name)
        self.window_title.set_title(game.name)
        self.window_title.set_subtitle(game.source_label or game.source)

        self.hero_title.set_label(game.name)
        subtitle = [game.source_label or game.source]
        if game.developer:
            subtitle.append(game.developer)
        if not game.installed:
            subtitle.append("nicht installiert")
        self.hero_subtitle.set_label("  ·  ".join(subtitle))
        self.banner.set_game(game)

        self.play_button.set_sensitive(bool(game.command))
        self.play_button.set_tooltip_text(
            "" if game.command else "Für dieses Spiel ist kein Startbefehl hinterlegt"
        )
        self.hide_content.set_label("Einblenden" if game.hidden else "Ausblenden")
        self.hide_content.set_icon_name(
            "view-reveal-symbolic" if game.hidden else "view-conceal-symbolic"
        )

        launcher = launcher_for(game.source)
        self.launcher_button.set_visible(launcher is not None)
        if launcher is not None:
            self.launcher_content.set_label(launcher[0])
            self.launcher_button.set_tooltip_text(
                f"{launcher[0]} öffnen, ohne das Spiel zu starten"
            )

        self._set_tags(game.categories)

        self.summary.set_label(game.summary or "")
        self.summary.set_visible(bool(game.summary))

        self._fact("playtime", humanise_playtime(game.play_seconds).capitalize())
        self._fact("last_played", humanise_date(game.last_played))
        self._fact("launches", f"{game.play_count}×" if game.play_count else "")
        self._fact("developer", game.developer)
        self._fact("publisher", game.publisher)
        self._fact("release", game.release_date)
        self._fact("source", game.source_label or game.source)
        self._fact("status", "installiert" if game.installed else "nicht installiert")
        self._fact("install_dir", game.install_dir)

    def _fact(self, key: str, value: str) -> None:
        """Fill a row, or hide it when we have nothing to put there."""
        row = self.fact_rows[key]
        row.set_subtitle(value or "")
        row.set_visible(bool(value))

    def _set_tags(self, categories: list[str]) -> None:
        child = self.tags.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.tags.remove(child)
            child = nxt
        for name in categories:
            label = Gtk.Label(label=name)
            label.add_css_class("category-tag")
            self.tags.append(label)
        self.tags.set_visible(bool(categories))

    def refresh_artwork(self) -> None:
        self.banner.refresh()
