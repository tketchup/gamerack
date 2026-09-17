"""Heroic Games Launcher: Epic, GOG, Amazon and sideloaded titles.

Heroic keeps a cached copy of each store's library as JSON, which is exactly
what we want — it includes artwork URLs and install state without us having to
talk to any store API.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import Game
from ..paths import HEROIC_ROOTS, all_existing

# file inside the heroic config dir -> (json key holding the list, runner, label)
LIBRARIES = [
    ("store_cache/legendary_library.json", "library", "legendary", "Epic Games"),
    ("store_cache/gog_library.json", "games", "gog", "GOG"),
    ("store_cache/nile_library.json", "library", "nile", "Amazon Games"),
    ("sideload_apps/library.json", "games", "sideload", "Heroic"),
]

# Heroic ships a few pseudo-entries that are not games.
SKIP_APP_NAMES = {"gog-redist"}


def heroic_root() -> Path | None:
    roots = all_existing(HEROIC_ROOTS)
    return roots[0] if roots else None


def _load(path: Path, key: str) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [g for g in data if isinstance(g, dict)]
    entries = data.get(key, [])
    return [g for g in entries if isinstance(g, dict)] if isinstance(entries, list) else []


def scan() -> list[Game]:
    root = heroic_root()
    if root is None:
        return []

    games: list[Game] = []
    for rel, key, runner, label in LIBRARIES:
        for entry in _load(root / rel, key):
            app_name = str(entry.get("app_name") or "").strip()
            title = str(entry.get("title") or "").strip()
            if not app_name or not title or app_name in SKIP_APP_NAMES:
                continue
            install = entry.get("install") or {}
            if install.get("is_dlc"):
                continue

            extra = entry.get("extra") if isinstance(entry.get("extra"), dict) else {}
            about = extra.get("about") if isinstance(extra.get("about"), dict) else {}
            genres = [str(g) for g in (extra.get("genres") or []) if g]
            summary = str(about.get("shortDescription") or about.get("description") or "")

            games.append(
                Game(
                    game_id=f"heroic:{runner}:{app_name}",
                    source="heroic",
                    source_label=label,
                    name=title,
                    developer=str(entry.get("developer") or ""),
                    command=["xdg-open", f"heroic://launch/{runner}/{app_name}"],
                    cover_hint=str(entry.get("art_square") or entry.get("art_cover") or ""),
                    # art_cover is the wide key art on Epic, art_background on GOG.
                    banner_hint=str(entry.get("art_background")
                                    or entry.get("art_cover") or ""),
                    categories=genres[:6],
                    summary=summary[:400],
                    install_dir=str(entry.get("folder_name") or install.get("install_path") or ""),
                    installed=bool(entry.get("is_installed")),
                )
            )
    return games
