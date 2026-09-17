"""Flatpak games, read from the exported .desktop entries.

We deliberately do not shell out to `flatpak list`: the exported entries carry
the Categories we need to tell a game from a text editor, and reading files is
both faster and safe to do on every scan.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from ..models import Game
from ..paths import DATA_HOME, all_existing
from .desktop import (GAME_CATEGORIES, LAUNCHER_IDS, NAME_BLOCKLIST,
                      _icon_path, categories_of)

EXPORT_DIRS = [
    Path("/var/lib/flatpak/exports/share/applications"),
    DATA_HOME / "flatpak/exports/share/applications",
]


def scan(scan_all: bool = False, hide_launchers: bool = True) -> list[Game]:
    games: dict[str, Game] = {}

    for directory in all_existing(EXPORT_DIRS):
        for path in directory.glob("*.desktop"):
            try:
                info = Gio.DesktopAppInfo.new_from_filename(str(path))
            except Exception:
                continue
            if info is None or info.get_nodisplay():
                continue

            # The X-Flatpak key holds the real application id; the filename
            # matches it for normal apps but not for exported sub-entries.
            app_id = info.get_string("X-Flatpak") or path.stem
            name = (info.get_display_name() or "").strip()
            if not name or NAME_BLOCKLIST.search(name):
                continue
            if hide_launchers and app_id in LAUNCHER_IDS:
                continue

            categories = set((info.get_categories() or "").strip(";").split(";"))
            if not (categories & GAME_CATEGORIES) and not scan_all:
                continue

            games[app_id] = Game(
                game_id=f"flatpak:{app_id}",
                source="flatpak",
                source_label="Flatpak",
                name=name,
                command=["flatpak", "run", app_id],
                cover_hint=_icon_path(info),
                categories=categories_of(info),
                summary=(info.get_description() or "")[:400],
                installed=True,
            )

    return list(games.values())
