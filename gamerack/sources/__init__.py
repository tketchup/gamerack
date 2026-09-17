"""Game sources. Each module exposes scan() -> list[Game]."""

from . import steam, heroic, lutris, flatpak, desktop

ALL = {
    "steam": steam,
    "heroic": heroic,
    "lutris": lutris,
    "flatpak": flatpak,
    "desktop": desktop,
}

__all__ = ["ALL", "steam", "heroic", "lutris", "flatpak", "desktop"]
