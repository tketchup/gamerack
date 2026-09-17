"""Filesystem locations Gamerack reads from and writes to."""

import os
from pathlib import Path

APP_ID = "io.github.tketchup.Gamerack"
APP_NAME = "Gamerack"


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


DATA_HOME = _xdg("XDG_DATA_HOME", ".local/share")
CONFIG_HOME = _xdg("XDG_CONFIG_HOME", ".config")
CACHE_HOME = _xdg("XDG_CACHE_HOME", ".cache")

DATA_DIR = DATA_HOME / "gamerack"
CONFIG_DIR = CONFIG_HOME / "gamerack"
CACHE_DIR = CACHE_HOME / "gamerack"

COVERS_DIR = DATA_DIR / "covers"
META_DIR = CACHE_DIR / "metadata"
LIBRARY_FILE = DATA_DIR / "library.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


def ensure_dirs() -> None:
    for d in (DATA_DIR, CONFIG_DIR, CACHE_DIR, COVERS_DIR, META_DIR):
        d.mkdir(parents=True, exist_ok=True)


# --- Locations of the launchers we scan -------------------------------------

STEAM_ROOTS = [
    DATA_HOME / "Steam",
    Path.home() / ".steam" / "steam",
    Path.home() / ".steam" / "root",
    DATA_HOME / "flatpak/app/com.valvesoftware.Steam/current/active/files/share/Steam",
    Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam",
]

HEROIC_ROOTS = [
    CONFIG_HOME / "heroic",
    Path.home() / ".var/app/com.heroicgameslauncher.hgl/config/heroic",
]

LUTRIS_ROOTS = [
    DATA_HOME / "lutris",
    Path.home() / ".var/app/net.lutris.Lutris/data/lutris",
]

DESKTOP_DIRS = [
    DATA_HOME / "applications",
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
    DATA_HOME / "flatpak/exports/share/applications",
]


def first_existing(candidates) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def all_existing(candidates) -> list[Path]:
    seen, out = set(), []
    for path in candidates:
        try:
            real = path.resolve()
        except OSError:
            continue
        if real in seen or not real.exists():
            continue
        seen.add(real)
        out.append(real)
    return out
