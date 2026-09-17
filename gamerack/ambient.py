"""Wide artwork for the ambient mode.

Steam's store records carry screenshots at exactly 1920x1080, which is the one
source in reach that is already 16:9 — covers are 2:3 and banners 1600x520, and
cropping either to a widescreen frame throws most of the picture away.

Nothing is fetched in advance. Three hundred screenshots would be some ninety
megabytes for a mode that may never start, so an image is downloaded when it is
about to be shown and the folder is trimmed back to the most recent few dozen.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from .covers import fetch_url
from .metadata import cached_details
from .models import Game
from .paths import CACHE_DIR

log = logging.getLogger(__name__)

AMBIENT_DIR = CACHE_DIR / "ambient"
# Roughly a dozen megabytes kept on disk; anything older is fetched again if
# the rotation comes back round to it.
KEEP_FILES = 45


def _safe(game_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in game_id)


def image_path(game: Game) -> Path:
    return AMBIENT_DIR / f"{_safe(game.game_id)}.jpg"


def screenshot_url(game: Game) -> str:
    """The first stored screenshot for this game, if the store knew one."""
    data = cached_details(game.steam_appid)
    if not data:
        return ""
    shots = data.get("screenshots")
    if not isinstance(shots, list):
        return ""
    for shot in shots:
        if isinstance(shot, dict) and shot.get("path_full"):
            return str(shot["path_full"])
    return ""


def has_image(game: Game) -> bool:
    """True when an image is available — on disk or known to be fetchable."""
    return image_path(game).exists() or bool(screenshot_url(game))


def candidates(games) -> list[Game]:
    """Only the games an ambient image exists for, as the mode requires."""
    return [g for g in games if has_image(g)]


def ensure_image(session: requests.Session, game: Game) -> Path | None:
    """The local file for this game, downloading it the first time."""
    path = image_path(game)
    if path.exists() and path.stat().st_size > 0:
        return path
    url = screenshot_url(game)
    if not url:
        return None
    data = fetch_url(session, url)
    if not data:
        return None
    try:
        AMBIENT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as error:
        log.info("Ambient-Bild nicht speicherbar: %s", error)
        return None
    trim()
    return path


def trim() -> None:
    """Keep the folder bounded; it is a cache and may be deleted at any time."""
    try:
        files = sorted(AMBIENT_DIR.glob("*.jpg"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for stale in files[KEEP_FILES:]:
        try:
            stale.unlink()
        except OSError:
            pass
