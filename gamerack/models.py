"""The Game record and the on-disk library."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .paths import LIBRARY_FILE

# Fields a user may override by hand. A rescan never touches these once set.
OVERRIDABLE = ("name", "developer", "command", "cover_path", "banner_path", "hidden")

# Which launcher a game belongs to, as far as the filters are concerned.
SOURCE_BUCKETS = {"steam": "steam", "heroic": "heroic", "lutris": "lutris"}

# Backlog score. Two factors, multiplied: how long the game has been left
# alone, and how little of it has been played. Hours already sunk in push the
# score down — eighty hours deep is not a backlog, it is a habit.
BACKLOG_IDLE_DAYS = 365.0      # untouched this long counts as fully idle
BACKLOG_HALF_HOURS = 6.0       # hours played that halve the score
# A game never started still gets a floor, higher when it is installed:
# going as far as putting it on the disk and then never launching it is the
# clearest backlog there is, and it is the one signal available on day one.
BACKLOG_FLOOR_INSTALLED = 0.78
BACKLOG_FLOOR_OWNED = 0.5


def humanise_playtime(seconds: int) -> str:
    if seconds <= 0:
        return "noch nicht gespielt"
    hours, minutes = divmod(seconds // 60, 60)
    if hours >= 10:
        return f"{hours} h gespielt"
    if hours:
        return f"{hours} h {minutes} min gespielt"
    return f"{minutes} min gespielt"


def humanise_backlog(score: int | None) -> str:
    if score is None:
        return ""
    if score >= 75:
        verdict = "längst fällig"
    elif score >= 50:
        verdict = "wäre mal dran"
    elif score >= 25:
        verdict = "kann warten"
    else:
        verdict = "läuft gerade"
    return f"{score} von 100 — {verdict}"


def humanise_date(stamp: float) -> str:
    if not stamp:
        return "nie"
    days = (time.time() - stamp) / 86400
    if days < 1:
        return "heute"
    if days < 2:
        return "gestern"
    if days < 7:
        return f"vor {int(days)} Tagen"
    return time.strftime("%d.%m.%Y", time.localtime(stamp))


@dataclass
class Game:
    game_id: str                 # "steam:730" — stable across rescans
    source: str                  # "steam", "heroic", "lutris", "flatpak", "desktop"
    name: str = ""
    command: list[str] = field(default_factory=list)
    developer: str = ""
    source_label: str = ""       # "Steam", "Epic Games", "GOG", ...
    installed: bool = True
    hidden: bool = False
    removed: bool = False        # source disappeared, but we keep user data

    cover_path: str = ""         # local file in COVERS_DIR
    cover_hint: str = ""         # URL or path the source suggested
    banner_path: str = ""        # wide artwork for the hero and the detail page
    banner_hint: str = ""
    steam_appid: str = ""        # lets us use Valve's CDN and match SteamGridDB

    # Extra metadata. Sources fill in what they know; metadata.py adds the rest.
    publisher: str = ""
    release_date: str = ""
    categories: list[str] = field(default_factory=list)
    summary: str = ""
    metadata_fetched: float = 0.0

    added: float = field(default_factory=time.time)
    last_played: float = 0.0
    play_count: int = 0
    play_seconds: int = 0

    install_dir: str = ""
    overrides: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Game":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def sort_name(self) -> str:
        return self.name.lower().removeprefix("the ").strip()

    @property
    def bucket(self) -> str:
        """The source filter this game falls under."""
        return SOURCE_BUCKETS.get(self.source, "other")

    @property
    def backlog_score(self) -> int | None:
        """0–100, how overdue this game is. None for anything not in a launcher.

        The clock for a game never started is `added`, the day Gamerack first
        saw it, because no launcher records when something was bought. That
        makes the score coarse at first — every unplayed game starts at the
        floor together — and sharper the longer the library is kept.
        """
        if self.bucket == "other":
            return None
        now = time.time()
        if self.play_seconds <= 0:
            idle = max(0.0, (now - self.added) / 86400)
            floor = (BACKLOG_FLOOR_INSTALLED if self.installed
                     else BACKLOG_FLOOR_OWNED)
            weight = max(floor, min(1.0, idle / BACKLOG_IDLE_DAYS))
        else:
            since = self.last_played or self.added
            idle = max(0.0, (now - since) / 86400)
            weight = min(1.0, idle / BACKLOG_IDLE_DAYS)
        hours = self.play_seconds / 3600
        weight *= BACKLOG_HALF_HOURS / (BACKLOG_HALF_HOURS + hours)
        return round(100 * weight)

    def apply_scan(self, fresh: "Game") -> bool:
        """Merge a freshly scanned record in, keeping user edits. True if changed."""
        changed = False

        # Playtime can come either from us (we timestamp launches) or from the
        # launcher's own records, whichever is further along.
        for f in ("last_played", "play_seconds"):
            if getattr(fresh, f) > getattr(self, f):
                setattr(self, f, getattr(fresh, f))
                changed = True

        # Artwork paths and the metadata timestamp are ours, not the source's;
        # everything else the source knows may be refreshed. Fields the source
        # has no opinion on come back empty and are skipped below, so metadata
        # fetched from elsewhere survives a rescan.
        for f in Game.__dataclass_fields__:
            if f in ("added", "last_played", "play_seconds", "play_count",
                     "overrides", "cover_path", "banner_path",
                     "metadata_fetched"):
                continue
            if f in self.overrides:
                continue
            new = getattr(fresh, f)
            if new not in ("", [], None) and getattr(self, f) != new:
                setattr(self, f, new)
                changed = True
        if self.removed:
            self.removed = False
            changed = True
        return changed

    def set_override(self, field_name: str, value) -> None:
        setattr(self, field_name, value)
        if field_name not in self.overrides:
            self.overrides.append(field_name)


class Library:
    """All known games, persisted as one JSON file."""

    def __init__(self, path: Path = LIBRARY_FILE, history=None):
        self.path = path
        self.history = history
        self.games: dict[str, Game] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for gid, data in raw.get("games", {}).items():
            try:
                self.games[gid] = Game.from_dict(data)
            except TypeError:
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "games": {gid: g.to_dict() for gid, g in self.games.items()},
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1))
        tmp.replace(self.path)

    # --- mutation -----------------------------------------------------------

    def merge(self, scanned: list[Game]) -> tuple[list[Game], list[Game]]:
        """Fold scan results into the library. Returns (new, updated)."""
        new, updated = [], []
        seen = set()
        for fresh in scanned:
            seen.add(fresh.game_id)
            existing = self.games.get(fresh.game_id)
            if existing is None:
                self.games[fresh.game_id] = fresh
                new.append(fresh)
                continue
            # Only a game we already knew can have played *since* — a new one
            # arrives with its whole total, which says nothing about when.
            before = existing.play_seconds
            if existing.apply_scan(fresh):
                updated.append(existing)
            if self.history is not None:
                self.history.played(existing.game_id,
                                    existing.play_seconds - before)
        # Anything a source used to report but no longer does is marked, not deleted:
        # the user may have edits or playtime attached to it.
        scanned_sources = {g.source for g in scanned}
        for game in self.games.values():
            if (
                game.source in scanned_sources
                and game.game_id not in seen
                and not game.removed
                and "command" not in game.overrides
            ):
                game.removed = True
        return new, updated

    def add(self, game: Game) -> None:
        self.games[game.game_id] = game

    def remove(self, game_id: str) -> None:
        self.games.pop(game_id, None)

    def visible(self, include_hidden: bool = False) -> list[Game]:
        return [
            g for g in self.games.values()
            if not g.removed and (include_hidden or not g.hidden)
        ]
