"""Lutris: read its SQLite catalogue (pga.db) read-only."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..models import Game
from ..paths import LUTRIS_ROOTS, all_existing

QUERY = """
    SELECT id, name, slug, runner, directory, installed, playtime, lastplayed
    FROM games
    WHERE name IS NOT NULL AND name != ''
"""


def lutris_root() -> Path | None:
    roots = all_existing(LUTRIS_ROOTS)
    return roots[0] if roots else None


def _artwork(root: Path, slug: str, subdirs: tuple[str, ...]) -> str:
    for sub in subdirs:
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            path = root / sub / f"{slug}{ext}"
            if path.exists():
                return str(path)
    return ""


def _cover(root: Path, slug: str) -> str:
    return _artwork(root, slug, ("coverart", "banners"))


def _banner(root: Path, slug: str) -> str:
    return _artwork(root, slug, ("banners",))


def scan() -> list[Game]:
    root = lutris_root()
    if root is None:
        return []
    db = root / "pga.db"
    if not db.exists():
        return []

    try:
        # Read-only URI so we never disturb a running Lutris.
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = conn.execute(QUERY).fetchall()
        conn.close()
    except sqlite3.Error:
        return []

    games = []
    for gid, name, slug, runner, directory, installed, playtime, lastplayed in rows:
        games.append(
            Game(
                game_id=f"lutris:{gid}",
                source="lutris",
                source_label="Lutris" + (f" ({runner})" if runner else ""),
                name=name.strip(),
                command=["lutris", f"lutris:rungameid/{gid}"],
                cover_hint=_cover(root, slug or ""),
                banner_hint=_banner(root, slug or ""),
                install_dir=directory or "",
                installed=bool(installed),
                play_seconds=int(float(playtime or 0) * 3600),
                last_played=float(lastplayed or 0),
            )
        )
    return games
