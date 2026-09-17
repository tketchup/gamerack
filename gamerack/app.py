"""Application entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from .config import Settings
from .models import Library
from .paths import APP_ID, ensure_dirs
from .ui.window import MainWindow

ACCELS = {
    "win.search": ["<Control>f"],
    "win.rescan": ["<Control>r"],
    "win.preferences": ["<Control>comma"],
    "win.about": ["F1"],
    "win.console": ["F11"],
    "app.quit": ["<Control>q", "<Control>w"],
    "win.view::grid": ["<Control>1"],
    "win.view::showcase": ["<Control>2"],
    "win.view::list": ["<Control>3"],
}


class GamerackApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window: MainWindow | None = None
        self.settings = Settings()
        self.library = Library()

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._load_css()

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)

        for name, accels in ACCELS.items():
            self.set_accels_for_action(name, accels)

    def do_activate(self):
        if self.window is None:
            self.window = MainWindow(self, self.library, self.settings)
            # Ctrl+F has no window action of its own; wire it to the toggle.
            search = Gio.SimpleAction.new("search", None)
            search.connect(
                "activate",
                lambda *_: self.window.search_button.set_active(
                    not self.window.search_button.get_active()
                ),
            )
            self.window.add_action(search)
        self.window.present()

    def do_shutdown(self):
        if self.window is not None:
            self.window.covers.stop()
            self.window.metadata.stop()
            if self.window.pads is not None:
                self.window.pads.stop()
        self.library.save()
        self.settings.save()
        Adw.Application.do_shutdown(self)

    def _load_css(self):
        css_file = Path(__file__).parent / "ui" / "style.css"
        if not css_file.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_file))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    ensure_dirs()
    return GamerackApp().run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
