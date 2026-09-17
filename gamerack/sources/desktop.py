"""Games that only exist as a .desktop entry in the application menu.

This is the catch-all: installers, emulators, itch.io builds, AppImages
registered by Gear Lever, and anything a launcher exported to the menu.
"""

from __future__ import annotations

import re
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from ..models import Game
from ..paths import DESKTOP_DIRS, all_existing

# Categories that make an entry a game without further questions.
GAME_CATEGORIES = {"Game", "ActionGame", "AdventureGame", "ArcadeGame",
                   "BoardGame", "BlocksGame", "CardGame", "KidsGame",
                   "LogicGame", "RolePlaying", "Shooter", "Simulation",
                   "SportsGame", "StrategyGame", "Emulator"}

# Entries we never want to list as a game, even when tagged Game.
NAME_BLOCKLIST = re.compile(
    r"(uninstall|deinstall|setup|readme|manual|handbuch|config(uration)?$|"
    r"support|website|homepage|crash|report|server|dedicated|editor$|"
    r"benchmark|launcher settings|eula)",
    re.I,
)

# Launchers we scan natively — listing their menu entry too would be noise,
# unless the user turns "hide launchers" off.
LAUNCHER_IDS = {
    "steam", "com.valvesoftware.Steam",
    "heroic", "com.heroicgameslauncher.hgl",
    "net.lutris.Lutris", "lutris",
    "com.usebottles.bottles",
}

FLATPAK_EXPORT_MARKERS = ("/flatpak/exports/", "/var/lib/flatpak/")

# The freedesktop category tokens, in words. "Game" itself says nothing that the
# rest of the window does not already, so it is left out.
CATEGORY_NAMES = {
    "ActionGame": "Action", "AdventureGame": "Adventure", "ArcadeGame": "Arcade",
    "BoardGame": "Brettspiel", "BlocksGame": "Geschicklichkeit",
    "CardGame": "Kartenspiel", "KidsGame": "Für Kinder", "LogicGame": "Logik",
    "RolePlaying": "Rollenspiel", "Shooter": "Shooter", "Simulation": "Simulation",
    "SportsGame": "Sport", "StrategyGame": "Strategie", "Emulator": "Emulator",
}


def categories_of(info: Gio.DesktopAppInfo) -> list[str]:
    tokens = (info.get_categories() or "").strip(";").split(";")
    return [CATEGORY_NAMES[t] for t in tokens if t in CATEGORY_NAMES]


def _iter_desktop_files(skip_flatpak: bool):
    for directory in all_existing(DESKTOP_DIRS):
        if skip_flatpak and any(m in str(directory) + "/" for m in FLATPAK_EXPORT_MARKERS):
            continue
        for path in directory.glob("*.desktop"):
            yield path


def _icon_path(info: Gio.DesktopAppInfo) -> str:
    """Resolve the entry's icon to a file we can show as a fallback cover."""
    icon = info.get_icon()
    if icon is None:
        return ""
    if isinstance(icon, Gio.FileIcon):
        return icon.get_file().get_path() or ""
    name = info.get_string("Icon") or ""
    if name.startswith("/") and Path(name).exists():
        return name
    return ""


def _is_game(info: Gio.DesktopAppInfo, scan_all: bool) -> bool:
    categories = set((info.get_categories() or "").strip(";").split(";"))
    if categories & GAME_CATEGORIES:
        return True
    return scan_all


def scan(scan_all: bool = False, hide_launchers: bool = True,
         skip_flatpak: bool = True) -> list[Game]:
    games: dict[str, Game] = {}

    for path in _iter_desktop_files(skip_flatpak):
        try:
            info = Gio.DesktopAppInfo.new_from_filename(str(path))
        except Exception:
            info = None
        if info is None or info.get_nodisplay() or info.get_is_hidden():
            continue

        name = (info.get_display_name() or "").strip()
        if not name or NAME_BLOCKLIST.search(name):
            continue
        if not _is_game(info, scan_all):
            continue

        desktop_id = path.stem
        if hide_launchers and desktop_id in LAUNCHER_IDS:
            continue
        # Our own menu entry is tagged Game so it lands in the right category;
        # that is no reason to list ourselves as a game.
        if info.get_string("X-Gamerack-Self"):
            continue

        # `gio launch` honours the entry's own Exec quoting, Path= and Terminal=.
        games[desktop_id] = Game(
            game_id=f"desktop:{desktop_id}",
            source="desktop",
            source_label="Anwendungsmenü",
            name=name,
            developer=info.get_string("X-Publisher") or "",
            command=["gio", "launch", str(path)],
            cover_hint=_icon_path(info),
            categories=categories_of(info),
            summary=(info.get_description() or "")[:400],
            install_dir=info.get_string("Path") or "",
            installed=True,
        )

    return list(games.values())
