"""Runs every enabled source and folds the results into the library."""

from __future__ import annotations

import logging
import re
import unicodedata

from .config import Settings
from .models import Game, Library
from .sources import ALL

log = logging.getLogger(__name__)

# A game found by a real launcher beats the same game found in the app menu.
SOURCE_PRIORITY = {"steam": 0, "heroic": 1, "lutris": 2, "flatpak": 3, "desktop": 4}


def normalise(name: str) -> str:
    """Loose key for spotting the same game reported by two sources."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"\b(the|a|an)\b", " ", text.lower())
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def dedupe(games: list[Game]) -> list[Game]:
    """Drop app-menu duplicates of games a launcher already reported."""
    games = sorted(games, key=lambda g: SOURCE_PRIORITY.get(g.source, 9))
    best: dict[str, Game] = {}
    for game in games:
        key = normalise(game.name)
        if not key:
            continue
        if key not in best:
            best[key] = game
    return list(best.values())


def run_scan(settings: Settings) -> list[Game]:
    """Scan all enabled sources. Safe to call off the main thread."""
    found: list[Game] = []

    for name, module in ALL.items():
        if not settings.source_enabled(name):
            continue
        try:
            if name == "desktop":
                result = module.scan(
                    scan_all=settings["desktop_scan_all"],
                    hide_launchers=settings["hide_launchers"],
                    skip_flatpak=settings.source_enabled("flatpak"),
                )
            elif name == "flatpak":
                result = module.scan(
                    scan_all=settings["desktop_scan_all"],
                    hide_launchers=settings["hide_launchers"],
                )
            else:
                result = module.scan()
        except Exception:
            log.exception("Quelle %s konnte nicht gelesen werden", name)
            continue
        log.info("%s: %d Einträge", name, len(result))
        found.extend(result)

    return dedupe(found)


def scan_into(library: Library, settings: Settings) -> tuple[list[Game], list[Game]]:
    new, updated = library.merge(run_scan(settings))
    library.save()
    return new, updated
