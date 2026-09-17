"""User settings, stored as plain JSON so they are easy to hand-edit."""

import json

from .paths import SETTINGS_FILE

DEFAULTS = {
    "view": "grid",                  # grid | showcase | list
    "sort": "name",                  # name | recent | added | playtime | backlog
    "show_hidden": False,
    "only_installed": False,
    "backlog_only": False,           # narrow the library to the backlog
    # Score a game needs to count as backlog. 60 means "installed and never
    # started, or started once and dropped"; lower it to reach the owned-but-
    # never-installed pile, which all sits just below.
    "backlog_min": 60,
    "cover_size": 200,               # width of a grid cover, in px
    "scan_on_start": True,
    "fetch_covers": True,
    "fetch_metadata": True,
    "steamgriddb_key": "",
    "sources": {                     # which launchers are scanned at all
        "steam": True,
        "heroic": True,
        "lutris": True,
        "flatpak": True,
        "desktop": True,
    },
    "filter_sources": {              # which of them the current view shows
        "steam": True,
        "heroic": True,
        "lutris": True,
        "other": True,
    },
    "desktop_scan_all": False,       # off: only entries that look like games
    "hide_launchers": False,
    "gamepad": True,                 # read /dev/input/js* for the console mode
    "ambient": True,                 # slideshow when the showcase sits idle
    "ambient_delay": 60,             # seconds of stillness before it starts
}


class Settings:
    def __init__(self, path=SETTINGS_FILE):
        self.path = path
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            stored = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for key, value in stored.items():
            # Merge the nested dicts rather than replacing them, so a settings
            # file written by an older version keeps the newer defaults.
            if key in ("sources", "filter_sources") and isinstance(value, dict):
                self.data[key].update(value)
            elif key in self.data:
                self.data[key] = value

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1))

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def source_enabled(self, name: str) -> bool:
        return bool(self.data["sources"].get(name, True))

    def set_source(self, name: str, enabled: bool):
        self.data["sources"][name] = enabled
        self.save()

    def bucket_shown(self, bucket: str) -> bool:
        return bool(self.data["filter_sources"].get(bucket, True))

    def set_bucket(self, bucket: str, shown: bool):
        self.data["filter_sources"][bucket] = shown
        self.save()
