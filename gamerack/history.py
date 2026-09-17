"""An append-only log of launches and observed playtime.

The launchers keep totals, not history: Steam's `localconfig.vdf` knows a
game's whole playtime and the day it was last touched, never a time series.
Anything the statistics page says about a week or a month therefore has to come
from records we write ourselves, and those begin the first time this version
runs. Older playing is gone for good — it was never written down anywhere.

One JSON object per line, appended and never rewritten, so a crash can at worst
cost the last line. Keys are short because the file grows for years:

    {"t": 1758067200.0, "e": "begin"}
    {"t": 1758067312.4, "e": "launch", "g": "steam:730"}
    {"t": 1758071000.0, "e": "play", "g": "steam:730", "s": 3600}
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .paths import HISTORY_FILE

log = logging.getLogger(__name__)

BEGIN = "begin"
LAUNCH = "launch"
PLAY = "play"

# A jump larger than this in one observation is treated as the launcher
# reporting a total for the first time rather than as time actually played
# since we last looked. Without it, a game whose playtime arrives late would
# dump its entire history into whichever day we happened to notice.
MAX_PLAUSIBLE_DELTA = 24 * 3600


class History:
    """The log, plus the aggregation the statistics page needs."""

    def __init__(self, path: Path = HISTORY_FILE):
        self.path = path
        self._events: list[dict] | None = None
        self._begin: float = 0.0

    # --- writing ------------------------------------------------------------

    def start(self) -> None:
        """Mark the log as open, so the page can name the day it starts from.

        Called at startup rather than on the first launch: a library that has
        not been played yet should still be able to say "recording since", and
        an empty week is a real answer instead of a missing one.
        """
        if self.path.exists():
            return
        self._write({"t": time.time(), "e": BEGIN})

    def _append(self, record: dict) -> None:
        self.start()
        self._write(record)

    def _write(self, record: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        except OSError as error:
            log.warning("Verlauf nicht schreibbar: %s", error)
            return
        if self._events is not None:
            self._events.append(record)
        if record.get("e") == BEGIN:
            self._begin = float(record["t"])

    def launched(self, game_id: str, at: float | None = None) -> None:
        self._append({"t": at or time.time(), "e": LAUNCH, "g": game_id})

    def played(self, game_id: str, seconds: int, at: float | None = None) -> None:
        """Record time the launcher reported on top of what we had before."""
        if seconds <= 0:
            return
        if seconds > MAX_PLAUSIBLE_DELTA:
            log.info("Verlauf: %s s für %s übersprungen, zu groß für eine Sitzung",
                     seconds, game_id)
            return
        self._append({"t": at or time.time(), "e": PLAY, "g": game_id,
                      "s": int(seconds)})

    def begin(self) -> float:
        """When the log starts — what the statistics page may honestly claim."""
        self.events()
        return self._begin

    # --- reading ------------------------------------------------------------

    def events(self) -> list[dict]:
        if self._events is None:
            self._events = self._read()
        return self._events

    def _read(self) -> list[dict]:
        events: list[dict] = []
        if not self.path.exists():
            return events
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            log.warning("Verlauf nicht lesbar: %s", error)
            return events
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue            # a torn last line costs that line, no more
            if isinstance(record, dict) and "t" in record:
                events.append(record)
        if events:
            self._begin = min(float(e["t"]) for e in events)
        return events

    def totals(self, since: float = 0.0,
               until: float | None = None) -> dict[str, dict[str, int]]:
        """Launches and seconds per game in a window, as {game_id: {...}}."""
        end = time.time() if until is None else until
        out: dict[str, dict[str, int]] = {}
        for event in self.events():
            stamp = float(event.get("t", 0))
            gid = event.get("g")
            if not gid or stamp < since or stamp > end:
                continue
            entry = out.setdefault(gid, {"launches": 0, "seconds": 0})
            if event.get("e") == LAUNCH:
                entry["launches"] += 1
            elif event.get("e") == PLAY:
                entry["seconds"] += int(event.get("s", 0))
        return out

    def active_days(self, since: float = 0.0,
                    until: float | None = None) -> int:
        """How many separate days saw any activity — for the average per day."""
        end = time.time() if until is None else until
        days = {
            time.strftime("%Y-%m-%d", time.localtime(float(e["t"])))
            for e in self.events()
            if e.get("e") in (LAUNCH, PLAY) and since <= float(e["t"]) <= end
        }
        return len(days)
