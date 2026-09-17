"""Extra metadata: genres, publisher, release date and a short description.

Most of it already sits in the launchers' own caches and is filled in while
scanning. What is missing we ask Valve's public store endpoint for — it answers
for any Steam app id, and `covers.steam_search` finds an id even for a game the
user owns somewhere else entirely.

Only empty fields are filled. Whatever a launcher reported, or the user typed,
stays as it is.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
import unicodedata

import requests

from .covers import new_session, steam_search
from .models import Game
from .paths import META_DIR

log = logging.getLogger(__name__)

APPDETAILS = "https://store.steampowered.com/api/appdetails?appids={appid}&l=german&cc=de"
TIMEOUT = 12

# Steam answers roughly 200 requests per five minutes before it starts refusing.
REQUEST_SPACING = 1.5

TAG_RE = re.compile(r"<[^>]+>")


def _key(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _plain(html: str, limit: int = 400) -> str:
    text = TAG_RE.sub(" ", html or "")
    text = (text.replace("&amp;", "&").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&nbsp;", " "))
    text = re.sub(r"\s+", " ", text).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text


def _cached(appid: str) -> dict | None:
    path = META_DIR / f"steam-{appid}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _store(appid: str, payload: dict) -> None:
    META_DIR.mkdir(parents=True, exist_ok=True)
    try:
        (META_DIR / f"steam-{appid}.json").write_text(json.dumps(payload))
    except OSError:
        pass


def appdetails(session: requests.Session, appid: str) -> dict | None:
    """The store's record for one app id, cached on disk between runs."""
    cached = _cached(appid)
    if cached is not None:
        return cached or None

    try:
        response = session.get(APPDETAILS.format(appid=appid), timeout=TIMEOUT)
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None

    entry = payload.get(str(appid)) if isinstance(payload, dict) else None
    if not isinstance(entry, dict) or not entry.get("success"):
        _store(appid, {})          # remember the miss; do not ask again
        return None
    data = entry.get("data")
    if not isinstance(data, dict):
        return None
    _store(appid, data)
    return data


def _match(game: Game, session: requests.Session) -> str:
    """The Steam app id for this game, if one can be found confidently."""
    if game.steam_appid:
        return game.steam_appid
    wanted = _key(game.name)
    if len(wanted) < 3:
        return ""
    for appid, name in steam_search(session, game.name, limit=5):
        if _key(name) == wanted:
            return appid
    return ""


def enrich(game: Game, session: requests.Session, allow_network: bool = True) -> bool:
    """Fill in what the game is still missing. True if anything changed."""
    if not allow_network:
        return False

    appid = _match(game, session)
    if not appid:
        game.metadata_fetched = time.time()
        return False

    data = appdetails(session, appid)
    game.metadata_fetched = time.time()
    if not data:
        return False

    changed = False

    def fill(field: str, value) -> None:
        nonlocal changed
        if value and not getattr(game, field) and field not in game.overrides:
            setattr(game, field, value)
            changed = True

    fill("developer", ", ".join(data.get("developers") or [])[:120])
    fill("publisher", ", ".join(data.get("publishers") or [])[:120])
    fill("release_date", str((data.get("release_date") or {}).get("date") or ""))
    fill("summary", _plain(data.get("short_description", "")))

    genres = [str(g.get("description")) for g in (data.get("genres") or [])
              if isinstance(g, dict) and g.get("description")]
    fill("categories", genres[:6])

    # A banner we can reach later without another store call.
    fill("banner_hint", data.get("background_raw") or data.get("header_image") or "")
    if not game.steam_appid:
        game.steam_appid = appid
        changed = True
    return changed


class MetadataFetcher:
    """One worker, deliberately: the store endpoint is rate limited."""

    def __init__(self, settings, on_ready):
        self.settings = settings
        self.on_ready = on_ready          # on_ready(game), from the worker
        # Two queues, because the library is worked through slowly in the
        # background: a game the user just opened must not wait behind three
        # hundred others.
        self.urgent: queue.Queue = queue.Queue()
        self.queue: queue.Queue = queue.Queue()
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last = 0.0
        threading.Thread(target=self._work, daemon=True, name="metadata").start()

    def request(self, game: Game, force: bool = False,
                urgent: bool = False) -> None:
        if not self.settings["fetch_metadata"]:
            return
        if not force and game.metadata_fetched:
            return
        with self._lock:
            if game.game_id in self._pending and not urgent:
                return
            self._pending.add(game.game_id)
        (self.urgent if urgent else self.queue).put(game)

    def request_many(self, games, force: bool = False) -> None:
        for game in games:
            self.request(game, force)

    def stop(self) -> None:
        self._stop.set()

    def _work(self) -> None:
        session = new_session()
        while not self._stop.is_set():
            urgent = True
            try:
                game = self.urgent.get_nowait()
            except queue.Empty:
                urgent = False
                try:
                    game = self.queue.get(timeout=0.5)
                except queue.Empty:
                    continue
            try:
                wait = REQUEST_SPACING - (time.monotonic() - self._last)
                if wait > 0:
                    if self._stop.wait(wait):
                        return
                self._last = time.monotonic()
                if enrich(game, session, self.settings["fetch_metadata"]):
                    self.on_ready(game)
            except Exception:
                log.debug("Metadaten für %s fehlgeschlagen", game.name, exc_info=True)
            finally:
                with self._lock:
                    self._pending.discard(game.game_id)
                (self.urgent if urgent else self.queue).task_done()
