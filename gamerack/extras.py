"""Installed Workshop mods for Steam games, for the detail page.

`appworkshop_<appid>.acf` in every library folder lists the workshop items
Steam has actually put on the disk, so the answer here is exact rather than a
guess. Only the titles have to come from the network, and a title never
changes, so they are cached for good.

DLC is deliberately absent: the store record names what *exists* for a game,
but no file on disk says which of them are yours, and a list that looks like an
inventory while really being a catalogue is worse than no list at all.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests
import vdf

from .paths import CACHE_DIR
from .sources.steam import library_dirs, steam_root

log = logging.getLogger(__name__)

WORKSHOP_DETAILS = ("https://api.steampowered.com/ISteamRemoteStorage"
                    "/GetPublishedFileDetails/v1/")
TIMEOUT = 12
# The endpoint takes a batch; a hundred keeps the request small enough to stay
# well inside the timeout even on a slow line.
BATCH = 100
TITLE_CACHE = CACHE_DIR / "workshop-titles.json"


def _titles_cached() -> dict[str, str]:
    try:
        data = json.loads(TITLE_CACHE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _titles_store(titles: dict[str, str]) -> None:
    try:
        TITLE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TITLE_CACHE.write_text(json.dumps(titles))
    except OSError as error:
        log.warning("Workshop-Titel nicht speicherbar: %s", error)


def installed_mods(appid: str) -> list[dict]:
    """Workshop items on disk for one app, newest change first.

    Titles are filled in later; this part needs no network and no waiting.
    """
    if not appid:
        return []
    root = steam_root()
    if root is None:
        return []

    out: list[dict] = []
    for steamapps in library_dirs(root):
        manifest = steamapps / "workshop" / f"appworkshop_{appid}.acf"
        if not manifest.exists():
            continue
        try:
            parsed = vdf.loads(manifest.read_text(errors="replace"))
        except (OSError, SyntaxError, ValueError):
            continue
        items = (parsed.get("AppWorkshop", {})
                       .get("WorkshopItemsInstalled", {}))
        if not isinstance(items, dict):
            continue
        for item_id, info in items.items():
            if not isinstance(info, dict):
                continue
            out.append({
                "id": str(item_id),
                "size": int(info.get("size", 0) or 0),
                "updated": float(info.get("timeupdated", 0) or 0),
                "title": "",
            })
    out.sort(key=lambda item: -item["updated"])
    return out


def mod_titles(session: requests.Session, ids: list[str],
               allow_network: bool = True) -> dict[str, str]:
    """Names for workshop ids, from the public endpoint. Cached permanently."""
    cache = _titles_cached()
    missing = [i for i in ids if i not in cache]
    if not missing or not allow_network:
        return {i: cache.get(i, "") for i in ids}

    fetched = False
    for start in range(0, len(missing), BATCH):
        chunk = missing[start:start + BATCH]
        form = {"itemcount": str(len(chunk))}
        for index, item_id in enumerate(chunk):
            form[f"publishedfileids[{index}]"] = item_id
        try:
            response = session.post(WORKSHOP_DETAILS, data=form, timeout=TIMEOUT)
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            log.info("Workshop-Titel nicht abrufbar: %s", error)
            break
        details = payload.get("response", {}).get("publishedfiledetails", [])
        for entry in details if isinstance(details, list) else []:
            if not isinstance(entry, dict):
                continue
            item_id = str(entry.get("publishedfileid", ""))
            if not item_id:
                continue
            # A deleted or private item answers with no title. Remember the
            # blank too, so we stop asking for something that will not come.
            cache[item_id] = entry.get("title", "") or ""
            fetched = True

    if fetched:
        _titles_store(cache)
    return {i: cache.get(i, "") for i in ids}


def humanise_size(size: int) -> str:
    if size <= 0:
        return ""
    for unit, step in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("kB", 1024)):
        if size >= step:
            value = size / step
            return f"{value:.1f} {unit}" if value < 10 else f"{round(value)} {unit}"
    return f"{size} B"


def humanise_updated(stamp: float) -> str:
    if not stamp:
        return ""
    return time.strftime("%d.%m.%Y", time.localtime(stamp))


def workshop_url(item_id: str) -> str:
    return f"https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"


def cache_path() -> Path:
    return TITLE_CACHE
