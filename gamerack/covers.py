"""Artwork: find it, normalise it, cache it on disk.

Two shapes are handled. A *cover* is the 2:3 poster the grid shows; a *banner*
is the wide image behind the showcase hero and the detail page.

Order of preference, cheapest first:
  1. artwork the user picked by hand
  2. artwork the launcher already downloaded (Steam's librarycache, Lutris)
  3. the artwork URL the launcher told us about (Heroic)
  4. Valve's CDN, for anything with a Steam app id
  5. SteamGridDB, if the user configured an API key
  6. the application icon, centred on a blurred backdrop

`search_artwork` is the manual counterpart: instead of taking the first hit it
collects everything the same sources offer so the user can choose.
"""

from __future__ import annotations

import io
import logging
import queue
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image, ImageFilter

from .models import Game
from .paths import COVERS_DIR

log = logging.getLogger(__name__)

COVER_W, COVER_H = 600, 900
BANNER_W, BANNER_H = 1600, 520
SGDB_API = "https://www.steamgriddb.com/api/v2"
STEAM_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/{file}"
STEAM_SEARCH = "https://steamcommunity.com/actions/SearchApps/{term}"
TIMEOUT = 12
USER_AGENT = "Gamerack/1.0 (+https://github.com/)"

COVER_FILES = ("library_600x900_2x.jpg", "library_600x900.jpg")
BANNER_FILES = ("library_hero.jpg", "header.jpg", "capsule_616x353.jpg")


def _safe(game_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", game_id)


def cover_file(game: Game) -> Path:
    # JPEG, not PNG: posters are photographic, and a few hundred of them as PNG
    # would cost well over a hundred megabytes for no visible gain.
    return COVERS_DIR / f"{_safe(game.game_id)}.jpg"


def banner_file(game: Game) -> Path:
    return COVERS_DIR / f"{_safe(game.game_id)}_banner.jpg"


def artwork_file(game: Game, kind: str) -> Path:
    return banner_file(game) if kind == "banner" else cover_file(game)


# --- image normalisation ----------------------------------------------------

def _to_poster(image: Image.Image) -> Image.Image:
    """Return a COVER_W x COVER_H PNG-ready image.

    Real posters are cropped to fill. Icons and other odd shapes are centred on
    a blurred, enlarged copy of themselves so the grid stays visually uniform.
    """
    image = image.convert("RGBA")
    src_ratio = image.width / image.height
    target_ratio = COVER_W / COVER_H

    # Anything roughly portrait is treated as real cover art.
    if 0.55 <= src_ratio <= 0.85:
        scale = max(COVER_W / image.width, COVER_H / image.height)
        resized = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.LANCZOS,
        )
        left = (resized.width - COVER_W) // 2
        top = (resized.height - COVER_H) // 2
        return resized.crop((left, top, left + COVER_W, top + COVER_H)).convert("RGB")

    # Everything else: blurred fill behind, whole image centred in front.
    scale = max(COVER_W / image.width, COVER_H / image.height)
    backdrop = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    left = (backdrop.width - COVER_W) // 2
    top = (backdrop.height - COVER_H) // 2
    backdrop = backdrop.crop((left, top, left + COVER_W, top + COVER_H))
    backdrop = backdrop.filter(ImageFilter.GaussianBlur(28))
    backdrop = Image.blend(backdrop.convert("RGB"), Image.new("RGB", backdrop.size, (24, 24, 28)), 0.35)

    inner = min(COVER_W, COVER_H) * (0.62 if src_ratio > 1.4 or src_ratio < 0.7 else 0.7)
    fit = min(inner / image.width, inner / image.height)
    if src_ratio > 1.4:  # wide banner: let it use the full width
        fit = (COVER_W * 0.92) / image.width
    front = image.resize(
        (max(1, round(image.width * fit)), max(1, round(image.height * fit))), Image.LANCZOS
    )
    backdrop.paste(
        front,
        ((COVER_W - front.width) // 2, (COVER_H - front.height) // 2),
        front,
    )
    return backdrop


def _to_banner(image: Image.Image) -> Image.Image:
    """Return a BANNER_W x BANNER_H image.

    Wide artwork is cropped to fill. Anything squarer than that — a poster, an
    icon — is laid over a blurred copy of itself, because cropping a portrait
    cover to a 3:1 strip leaves nothing recognisable.
    """
    image = image.convert("RGBA")
    src_ratio = image.width / image.height

    def _fill(source: Image.Image) -> Image.Image:
        scale = max(BANNER_W / source.width, BANNER_H / source.height)
        resized = source.resize(
            (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
            Image.LANCZOS,
        )
        left = (resized.width - BANNER_W) // 2
        top = (resized.height - BANNER_H) // 3   # upper third: key art usually sits high
        top = max(0, min(top, resized.height - BANNER_H))
        return resized.crop((left, top, left + BANNER_W, top + BANNER_H))

    if src_ratio >= 1.6:
        return _fill(image).convert("RGB")

    backdrop = _fill(image).filter(ImageFilter.GaussianBlur(34))
    backdrop = Image.blend(
        backdrop.convert("RGB"), Image.new("RGB", backdrop.size, (18, 18, 22)), 0.4
    )
    fit = (BANNER_H * 0.86) / image.height
    front = image.resize(
        (max(1, round(image.width * fit)), max(1, round(image.height * fit))), Image.LANCZOS
    )
    backdrop.paste(
        front,
        ((BANNER_W - front.width) // 2, (BANNER_H - front.height) // 2),
        front,
    )
    return backdrop


def save_artwork(game: Game, data: bytes | Path, kind: str = "cover") -> str:
    """Normalise `data` into the artwork cache. Returns the path, or ""."""
    try:
        if isinstance(data, Path):
            image = Image.open(data)
        else:
            image = Image.open(io.BytesIO(data))
        shaped = _to_banner(image) if kind == "banner" else _to_poster(image)
    except Exception:
        log.debug("Bild für %s nicht lesbar", game.name, exc_info=True)
        return ""

    target = artwork_file(game, kind)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shaped.convert("RGB").save(target, "JPEG", quality=88, optimize=True,
                                   progressive=True)
    except OSError:
        return ""
    return str(target)


def save_cover(game: Game, data: bytes | Path) -> str:
    return save_artwork(game, data, "cover")


# --- remote lookups ---------------------------------------------------------

def new_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def fetch_url(session: requests.Session, url: str) -> bytes | None:
    try:
        response = session.get(url, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if response.status_code != 200 or not response.content:
        return None
    if "image" not in response.headers.get("Content-Type", "image"):
        return None
    return response.content


def steam_cdn_urls(appid: str, kind: str) -> list[str]:
    names = BANNER_FILES if kind == "banner" else COVER_FILES
    return [STEAM_CDN.format(appid=appid, file=name) for name in names]


def steam_cdn(session: requests.Session, appid: str, kind: str = "cover") -> bytes | None:
    for url in steam_cdn_urls(appid, kind):
        data = fetch_url(session, url)
        if data:
            return data
    return None


def steam_search(session: requests.Session, term: str, limit: int = 5) -> list[tuple[str, str]]:
    """Ask Steam's own app search for candidate app ids. [(appid, name), ...]

    This is what lets a game bought on Epic or GOG still pick up Valve's
    artwork: we do not need the game to be on Steam for *us*, only for Steam.
    """
    if not term.strip():
        return []
    try:
        response = session.get(
            STEAM_SEARCH.format(term=requests.utils.quote(term.strip())), timeout=TIMEOUT
        )
        payload = response.json()
    except (requests.RequestException, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    results = []
    for entry in payload[:limit]:
        if isinstance(entry, dict) and entry.get("appid"):
            results.append((str(entry["appid"]), str(entry.get("name") or "")))
    return results


def _sgdb_json(session: requests.Session, key: str, url: str):
    try:
        r = session.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
        if r.status_code == 200:
            payload = r.json()
            if payload.get("success"):
                return payload.get("data")
    except (requests.RequestException, ValueError):
        pass
    return None


def sgdb_game_id(session: requests.Session, key: str, game: Game,
                 term: str = "") -> int | None:
    if game.steam_appid and not term:
        data = _sgdb_json(session, key, f"{SGDB_API}/games/steam/{game.steam_appid}")
        if isinstance(data, dict) and data.get("id"):
            return data["id"]
    query = requests.utils.quote(term or game.name)
    data = _sgdb_json(session, key, f"{SGDB_API}/search/autocomplete/{query}")
    if isinstance(data, list) and data:
        return data[0].get("id")
    return None


def sgdb_urls(session: requests.Session, key: str, game: Game, kind: str,
              term: str = "", limit: int = 12) -> list[str]:
    """Artwork URLs from SteamGridDB, most highly rated first."""
    sgdb_id = sgdb_game_id(session, key, game, term)
    if sgdb_id is None:
        return []
    if kind == "banner":
        endpoint = f"{SGDB_API}/heroes/game/{sgdb_id}?types=static&nsfw=false"
    else:
        endpoint = (f"{SGDB_API}/grids/game/{sgdb_id}"
                    "?dimensions=600x900,342x482&types=static&nsfw=false")
    items = _sgdb_json(session, key, endpoint)
    if not isinstance(items, list):
        return []
    return [i["url"] for i in items[:limit] if isinstance(i, dict) and i.get("url")]


def steamgriddb(session: requests.Session, key: str, game: Game,
                kind: str = "cover") -> bytes | None:
    """Look the game up on SteamGridDB and take the top-voted artwork."""
    for url in sgdb_urls(session, key, game, kind, limit=3):
        data = fetch_url(session, url)
        if data:
            return data
    return None


def resolve(game: Game, session: requests.Session, sgdb_key: str = "",
            allow_network: bool = True, kind: str = "cover") -> str:
    """Find and cache artwork for one game. Returns the local path, or ""."""
    current = game.banner_path if kind == "banner" else game.cover_path
    if current and Path(current).exists():
        return current

    cached = artwork_file(game, kind)
    if cached.exists() and cached.stat().st_size > 0:
        return str(cached)

    hint = (game.banner_hint if kind == "banner" else game.cover_hint) or ""
    if hint and not hint.startswith(("http://", "https://")):
        path = Path(hint)
        if path.exists():
            saved = save_artwork(game, path, kind)
            if saved:
                return saved

    if not allow_network:
        return ""

    if hint.startswith(("http://", "https://")):
        data = fetch_url(session, hint)
        if data:
            saved = save_artwork(game, data, kind)
            if saved:
                return saved

    if game.steam_appid:
        data = steam_cdn(session, game.steam_appid, kind)
        if data:
            saved = save_artwork(game, data, kind)
            if saved:
                return saved

    if sgdb_key:
        data = steamgriddb(session, sgdb_key, game, kind)
        if data:
            saved = save_artwork(game, data, kind)
            if saved:
                return saved

    return ""


# --- manual search ----------------------------------------------------------

def search_artwork(game: Game, term: str, kind: str, sgdb_key: str,
                   on_item, should_stop, limit: int = 24) -> int:
    """Collect artwork candidates from every source and hand them over one by one.

    `on_item(label, data)` is called for each image that actually downloaded and
    decoded; `should_stop()` lets the dialog abandon a search the user has moved
    on from. Runs on a worker thread. Returns how many candidates were offered.
    """
    session = new_session()
    jobs: list[tuple[str, str]] = []   # (label, url)

    hint = (game.banner_hint if kind == "banner" else game.cover_hint) or ""
    if hint.startswith(("http://", "https://")):
        jobs.append((game.source_label or game.source, hint))

    # Anything Steam knows about, whether or not the game came from Steam.
    appids = [game.steam_appid] if game.steam_appid else []
    for appid, _name in steam_search(session, term):
        if appid not in appids:
            appids.append(appid)
    for appid in appids[:4]:
        for url in steam_cdn_urls(appid, kind):
            jobs.append(("Steam", url))

    if sgdb_key:
        for url in sgdb_urls(session, sgdb_key, game, kind, term=term, limit=limit):
            jobs.append(("SteamGridDB", url))

    seen: set[str] = set()
    jobs = [(label, url) for label, url in jobs
            if not (url in seen or seen.add(url))][:limit]
    if not jobs or should_stop():
        return 0

    delivered = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for (label, url), data in zip(jobs, pool.map(
            lambda job: fetch_url(session, job[1]), jobs
        )):
            if should_stop():
                break
            if data:
                delivered += 1
                on_item(label, data)
    return delivered


# --- background worker ------------------------------------------------------

class CoverFetcher:
    """A small thread pool that resolves artwork without blocking the UI."""

    def __init__(self, settings, on_ready, workers: int = 6):
        self.settings = settings
        self.on_ready = on_ready          # on_ready(game, kind), from a worker
        self.queue: queue.Queue = queue.Queue()
        self._pending: set[tuple[str, str]] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.threads = [
            threading.Thread(target=self._work, daemon=True, name=f"cover-{i}")
            for i in range(workers)
        ]
        for thread in self.threads:
            thread.start()

    def request(self, game: Game, kind: str = "cover") -> None:
        current = game.banner_path if kind == "banner" else game.cover_path
        if current and Path(current).exists():
            return
        key = (game.game_id, kind)
        with self._lock:
            if key in self._pending:
                return
            self._pending.add(key)
        self.queue.put((game, kind))

    def request_many(self, games, kind: str = "cover") -> None:
        for game in games:
            self.request(game, kind)

    def stop(self) -> None:
        self._stop.set()

    def _work(self) -> None:
        session = new_session()
        while not self._stop.is_set():
            try:
                game, kind = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                path = resolve(
                    game,
                    session,
                    sgdb_key=self.settings["steamgriddb_key"],
                    allow_network=self.settings["fetch_covers"],
                    kind=kind,
                )
                if path:
                    if kind == "banner":
                        game.banner_path = path
                    else:
                        game.cover_path = path
                    self.on_ready(game, kind)
            except Exception:
                log.debug("Artwork für %s fehlgeschlagen", game.name, exc_info=True)
            finally:
                with self._lock:
                    self._pending.discard((game.game_id, kind))
                self.queue.task_done()
