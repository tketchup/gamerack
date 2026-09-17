"""Steam: installed apps from the appmanifests, plus non-Steam shortcuts."""

from __future__ import annotations

import binascii
import re
from pathlib import Path

import vdf

from ..models import Game
from ..paths import STEAM_ROOTS, all_existing

# Runtimes, redistributables and Proton builds are apps in Steam's eyes but
# nothing you would ever launch from a library.
SKIP_PATTERNS = (
    re.compile(r"^Steam(works)? Linux Runtime", re.I),
    re.compile(r"^Steamworks Common Redistributables", re.I),
    re.compile(r"^Proton\b", re.I),
    re.compile(r"^Steam Linux Runtime", re.I),
    re.compile(r"^SteamVR", re.I),
)
SKIP_APPIDS = {"228980", "1070560", "1391110", "1628350", "1493710", "1887720"}


def steam_root() -> Path | None:
    roots = all_existing(STEAM_ROOTS)
    return roots[0] if roots else None


def library_dirs(root: Path) -> list[Path]:
    """Every steamapps/ directory Steam knows about, across all drives."""
    dirs = [root / "steamapps"]
    vdf_file = root / "steamapps" / "libraryfolders.vdf"
    if not vdf_file.exists():
        return [d for d in dirs if d.exists()]
    try:
        parsed = vdf.load(vdf_file.open(encoding="utf-8", errors="replace"))
    except Exception:
        return [d for d in dirs if d.exists()]
    for entry in parsed.get("libraryfolders", {}).values():
        if isinstance(entry, dict) and entry.get("path"):
            dirs.append(Path(entry["path"]) / "steamapps")
    return all_existing(dirs)


def _should_skip(appid: str, name: str) -> bool:
    if appid in SKIP_APPIDS:
        return True
    return any(p.search(name) for p in SKIP_PATTERNS)


def _local_cover(root: Path, appid: str) -> str:
    """Steam already downloaded the artwork; reuse it instead of hitting the net."""
    candidates = [
        root / "appcache/librarycache" / appid / "library_600x900.jpg",
        root / "appcache/librarycache" / f"{appid}_library_600x900.jpg",
        root / "appcache/librarycache" / appid / "library_600x900_2x.jpg",
    ]
    for path in candidates:
        if path.exists() and path.stat().st_size > 0:
            return str(path)
    return ""


def _local_banner(root: Path, appid: str) -> str:
    """The wide hero image, if Steam has already cached it."""
    candidates = [
        root / "appcache/librarycache" / appid / "library_hero.jpg",
        root / "appcache/librarycache" / f"{appid}_library_hero.jpg",
        root / "appcache/librarycache" / appid / "header.jpg",
    ]
    for path in candidates:
        if path.exists() and path.stat().st_size > 0:
            return str(path)
    return ""


def _playtimes(root: Path) -> dict[str, tuple[int, float]]:
    """appid -> (seconds played, last played) from each user's local config."""
    result: dict[str, tuple[int, float]] = {}
    userdata = root / "userdata"
    if not userdata.exists():
        return result

    for user_dir in userdata.iterdir():
        config = user_dir / "config" / "localconfig.vdf"
        if not config.exists():
            continue
        try:
            parsed = vdf.load(config.open(encoding="utf-8", errors="replace"))
        except Exception:
            continue

        node = parsed.get("UserLocalConfigStore", {})
        for key in ("Software", "Valve", "Steam", "apps"):
            node = next(
                (v for k, v in node.items() if k.lower() == key.lower()
                 and isinstance(v, dict)),
                {},
            )
            if not node:
                break

        for appid, entry in node.items():
            if not isinstance(entry, dict):
                continue
            lowered = {k.lower(): v for k, v in entry.items()}
            try:
                seconds = int(lowered.get("playtime", 0)) * 60
                played = float(lowered.get("lastplayed", 0))
            except (TypeError, ValueError):
                continue
            if seconds or played:
                previous = result.get(appid, (0, 0.0))
                result[appid] = (max(previous[0], seconds), max(previous[1], played))
    return result


def _scan_shortcuts(root: Path) -> list[Game]:
    """Non-Steam games the user added to their Steam library."""
    games = []
    userdata = root / "userdata"
    if not userdata.exists():
        return games
    for user_dir in userdata.iterdir():
        shortcuts = user_dir / "config" / "shortcuts.vdf"
        if not shortcuts.exists():
            continue
        try:
            data = vdf.binary_load(shortcuts.open("rb"))
        except Exception:
            continue
        for entry in data.get("shortcuts", {}).values():
            if not isinstance(entry, dict):
                continue
            name = (entry.get("AppName") or entry.get("appname") or "").strip()
            exe = (entry.get("Exe") or entry.get("exe") or "").strip().strip('"')
            if not name or not exe:
                continue
            appid = entry.get("appid")
            # Steam stores shortcut ids as signed 32-bit; the URL form is unsigned.
            gameid = str((int(appid) & 0xFFFFFFFF) << 32 | 0x02000000) if appid else ""
            games.append(
                Game(
                    game_id=f"steam:shortcut:{appid or binascii.crc32(name.encode())}",
                    source="steam",
                    source_label="Steam (Verknüpfung)",
                    name=name,
                    command=["xdg-open", f"steam://rungameid/{gameid}"] if gameid
                    else ["sh", "-c", exe],
                    install_dir=(entry.get("StartDir") or "").strip('"'),
                    installed=True,
                )
            )
    return games


def scan() -> list[Game]:
    root = steam_root()
    if root is None:
        return []

    games: list[Game] = []
    playtimes = _playtimes(root)
    for steamapps in library_dirs(root):
        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                state = vdf.load(manifest.open(encoding="utf-8", errors="replace"))["AppState"]
            except Exception:
                continue
            appid = str(state.get("appid", "")).strip()
            name = (state.get("name") or "").strip()
            if not appid or not name or _should_skip(appid, name):
                continue
            install_dir = steamapps / "common" / state.get("installdir", "")
            seconds, played = playtimes.get(appid, (0, 0.0))
            games.append(
                Game(
                    game_id=f"steam:{appid}",
                    source="steam",
                    source_label="Steam",
                    name=name,
                    command=["xdg-open", f"steam://rungameid/{appid}"],
                    steam_appid=appid,
                    cover_hint=_local_cover(root, appid),
                    banner_hint=_local_banner(root, appid),
                    install_dir=str(install_dir) if install_dir.exists() else "",
                    installed=True,
                    play_seconds=seconds,
                    last_played=played,
                )
            )

    games.extend(_scan_shortcuts(root))
    return games
