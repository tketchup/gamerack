"""Starting a launcher on its own, without launching a game.

Useful for the things Gamerack deliberately does not do: installing, updating,
managing cloud saves. We only offer the button when the launcher is actually
here — a native binary first, a Flatpak second.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .paths import DATA_HOME

# source -> (label, native binary, flatpak app id, fallback command)
LAUNCHERS = {
    "steam": ("Steam", "steam", "com.valvesoftware.Steam",
              ["xdg-open", "steam://open/games"]),
    "heroic": ("Heroic", "heroic", "com.heroicgameslauncher.hgl", None),
    "lutris": ("Lutris", "lutris", "net.lutris.Lutris", None),
}

FLATPAK_EXPORTS = [
    DATA_HOME / "flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
]


def _flatpak_installed(app_id: str) -> bool:
    return any((d / f"{app_id}.desktop").exists() for d in FLATPAK_EXPORTS)


def launcher_for(source: str) -> tuple[str, list[str]] | None:
    """(label, command) for a game's launcher, or None if there is nothing to open."""
    entry = LAUNCHERS.get(source)
    if entry is None:
        return None
    label, binary, app_id, fallback = entry

    if shutil.which(binary):
        return label, [binary]
    if _flatpak_installed(app_id):
        return label, ["flatpak", "run", app_id]
    if fallback:
        return label, fallback
    return None
