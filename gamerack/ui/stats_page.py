"""The statistics page: what was played in a period, and how much.

Everything here is read out of `history.jsonl`, which Gamerack started writing
the first time this version ran. The launchers keep totals only, so a period
that reaches back before that day has nothing to show and says so rather than
inventing a figure.
"""

from __future__ import annotations

import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk, Pango  # noqa: E402

from ..history import History
from ..models import Library, humanise_playtime
from .widgets import TEXTURES, Thumbnail, initials, placeholder_class

# Rolling windows, counted back from now — a "week" is the last seven days
# rather than the calendar week, which is what you want when you ask what you
# have been playing lately.
PERIODS = [
    ("week", "Woche", 7),
    ("month", "Monat", 30),
    ("year", "Jahr", 365),
    ("ever", "Jemals", 0),
    ("custom", "Eigener", -1),
]

METRICS = [("playtime", "Spielzeit"), ("launches", "Starts")]

THUMB_W, THUMB_H = 40, 60
TOP_N = 50


def _short_playtime(seconds: int) -> str:
    if seconds <= 0:
        return "—"
    hours, minutes = divmod(seconds // 60, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min"


def _day_start(stamp: float) -> float:
    parts = time.localtime(stamp)
    return time.mktime((parts.tm_year, parts.tm_mon, parts.tm_mday,
                        0, 0, 0, 0, 0, -1))


class StatsPage(Adw.NavigationPage):
    """One reusable page; `refresh` rebuilds it from the log."""

    __gtype_name__ = "GamerackStatsPage"

    __gsignals__ = {
        "open-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, library: Library, history: History):
        super().__init__(title="Statistik", tag="stats")
        self.library = library
        self.history = history
        self.period = "month"
        self.metric = "playtime"
        now = time.time()
        self._from = _day_start(now - 30 * 86400)
        self._to = now

        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title="Statistik"))
        header.add_css_class("flat")

        self.toolbar = Adw.ToolbarView()
        self.toolbar.add_top_bar(header)
        self.toolbar.set_content(self._build_body())
        self.set_child(self.toolbar)

    # --- construction -------------------------------------------------------

    def _build_body(self) -> Gtk.Widget:
        self.period_group = Adw.ToggleGroup(halign=Gtk.Align.CENTER)
        for key, label, _days in PERIODS:
            self.period_group.add(Adw.Toggle(name=key, label=label))
        self.period_group.set_active_name(self.period)
        self.period_group.connect("notify::active-name", self._on_period)

        self.range_row = self._build_range_row()

        self.note = Gtk.Label(xalign=0.5, wrap=True, justify=Gtk.Justification.CENTER)
        self.note.add_css_class("stats-note")

        self.tiles = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                 homogeneous=True, column_spacing=12,
                                 row_spacing=12, min_children_per_line=2,
                                 max_children_per_line=4)

        self.metric_group = Adw.ToggleGroup(halign=Gtk.Align.START)
        for key, label in METRICS:
            self.metric_group.add(Adw.Toggle(name=key, label=label))
        self.metric_group.set_active_name(self.metric)
        self.metric_group.connect("notify::active-name", self._on_metric)

        heading = Gtk.Label(label="Bestenliste", xalign=0, hexpand=True)
        heading.add_css_class("title-4")
        head_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        head_row.append(heading)
        head_row.append(self.metric_group)

        self.ranking = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.ranking.add_css_class("boxed-list")
        self.ranking.connect("row-activated", self._on_row)

        self.empty = Adw.StatusPage(
            icon_name="document-open-recent-symbolic",
            title="Noch nichts aufgezeichnet",
            description="In diesem Zeitraum wurde kein Spiel gestartet.",
            vexpand=True,
        )

        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.results.append(head_row)
        self.results.append(self.ranking)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                          margin_top=18, margin_bottom=30)
        content.append(self.period_group)
        content.append(self.range_row)
        content.append(self.note)
        content.append(self.tiles)
        content.append(self.results)
        content.append(self.empty)

        clamp = Adw.Clamp(maximum_size=820, tightening_threshold=640,
                          child=content, margin_start=18, margin_end=18)
        return Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vexpand=True, child=clamp)

    def _build_range_row(self) -> Gtk.Widget:
        self.from_button = self._date_button(True)
        self.to_button = self._date_button(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                      halign=Gtk.Align.CENTER)
        box.append(Gtk.Label(label="von"))
        box.append(self.from_button)
        box.append(Gtk.Label(label="bis"))
        box.append(self.to_button)
        box.set_visible(False)
        return box

    def _date_button(self, is_start: bool) -> Gtk.MenuButton:
        calendar = Gtk.Calendar()
        calendar.connect("day-selected", self._on_date, is_start)
        button = Gtk.MenuButton(popover=Gtk.Popover(child=calendar))
        button.calendar = calendar
        return button

    # --- period and metric --------------------------------------------------

    def _on_period(self, group, _param) -> None:
        self.period = group.get_active_name() or "month"
        self.range_row.set_visible(self.period == "custom")
        if self.period != "custom":
            days = dict((k, d) for k, _l, d in PERIODS)[self.period]
            self._to = time.time()
            self._from = 0.0 if days == 0 else _day_start(self._to - days * 86400)
        self.refresh()

    def _on_metric(self, group, _param) -> None:
        self.metric = group.get_active_name() or "playtime"
        self.refresh()

    def _on_date(self, calendar, is_start: bool) -> None:
        chosen = calendar.get_date()
        stamp = chosen.to_unix()
        if is_start:
            self._from = _day_start(stamp)
        else:
            # Inclusive: picking today must count what happened today.
            self._to = _day_start(stamp) + 86400 - 1
        self.refresh()

    def _on_row(self, _box, row) -> None:
        game_id = getattr(row, "game_id", "")
        if game_id:
            self.emit("open-requested", game_id)

    # --- population ---------------------------------------------------------

    def _totals(self) -> dict[str, dict[str, int]]:
        """Where the figures come from, which differs by period.

        "Ever" is answerable without our log: the launchers keep a running
        total per game, and that is complete back to the day it was bought.
        What they never kept is *when* — so every bounded period has to come
        from the log instead, and starts there from nothing.
        """
        if self.period == "ever":
            return self._library_totals()
        return self.history.totals(self._from, self._to)

    def _library_totals(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for game_id, game in self.library.games.items():
            if game.removed:
                continue
            if game.play_seconds or game.play_count:
                out[game_id] = {"seconds": int(game.play_seconds),
                                "launches": int(game.play_count)}
        return out

    def refresh(self) -> None:
        self._sync_date_buttons()
        totals = self._totals()
        rows = self._rank(totals)

        self._fill_note()
        self._fill_tiles(totals, rows)

        for child in list(self.ranking):
            self.ranking.remove(child)
        for index, (game_id, entry) in enumerate(rows[:TOP_N], start=1):
            self.ranking.append(self._row(index, game_id, entry, rows[0][1]))

        has_rows = bool(rows)
        self.results.set_visible(has_rows)
        self.tiles.set_visible(has_rows)
        self.empty.set_visible(not has_rows)
        if not has_rows:
            # An empty log and an empty period are different problems, and on
            # the first day it is the former — say what fills it.
            nothing_at_all = not self.history.totals() and not self._library_totals()
            self.empty.set_description(
                "Starte ein Spiel aus Gamerack heraus, dann erscheint es hier. "
                "Spielzeit, die ein Launcher nachmeldet, kommt beim nächsten "
                "Suchlauf dazu."
                if nothing_at_all else
                "In diesem Zeitraum wurde kein Spiel gestartet."
            )
            self.empty.set_title("Noch nichts aufgezeichnet" if nothing_at_all
                                 else "Nichts in diesem Zeitraum")

    def _rank(self, totals: dict) -> list[tuple[str, dict]]:
        key = "seconds" if self.metric == "playtime" else "launches"
        rows = [(gid, entry) for gid, entry in totals.items()
                if entry["seconds"] or entry["launches"]]
        rows.sort(key=lambda item: (-item[1][key], -item[1]["seconds"],
                                    self._name(item[0]).lower()))
        return rows

    def _name(self, game_id: str) -> str:
        game = self.library.games.get(game_id)
        return game.name if game is not None else game_id

    def _sync_date_buttons(self) -> None:
        for button, stamp in ((self.from_button, self._from),
                              (self.to_button, self._to)):
            when = stamp or time.time()
            button.set_label(time.strftime("%d.%m.%Y", time.localtime(when)))

    def _fill_note(self) -> None:
        begin = self.history.begin()
        started = (time.strftime("%d.%m.%Y", time.localtime(begin))
                   if begin else "")

        if self.period == "ever":
            # Two sources in one view, so say which is which: the playtime is
            # the launcher's running total and complete, the start count is
            # only what we have seen ourselves.
            self.note.set_label(
                "Die Spielzeit ist der Gesamtstand aus den Launchern. Die "
                "Starts zählt Gamerack selbst"
                + (f", seit {started}." if started else ".")
            )
            self.note.set_visible(True)
            return

        if not begin:
            self.note.set_label("Die Aufzeichnung hat noch nicht begonnen.")
            self.note.set_visible(True)
            return
        if self._from and self._from >= begin:
            self.note.set_visible(False)
            return
        # The honest caveat: the launchers kept totals but never a time series,
        # so a bounded period cannot reach further back than our own log.
        self.note.set_label(
            f"Aufgezeichnet wird seit {started}. Was davor gespielt wurde, "
            "lässt sich keinem Zeitraum zuordnen — es steckt nur in „Jemals“."
        )
        self.note.set_visible(True)

    def _fill_tiles(self, totals: dict, rows: list) -> None:
        for child in list(self.tiles):
            self.tiles.remove(child)

        seconds = sum(e["seconds"] for e in totals.values())
        launches = sum(e["launches"] for e in totals.values())

        # Four tiles, so they sit in one row. There is deliberately no
        # "most played" tile: that is rank one of the list directly below.
        # The fourth one differs by period, because "per active day" needs the
        # log, which for "ever" is not where the figures came from.
        if self.period == "ever":
            fourth = ("Ø pro Spiel",
                      _short_playtime(round(seconds / len(rows))) if rows else "—")
        else:
            days = self.history.active_days(self._from, self._to)
            fourth = (f"Ø von {days} aktiven Tagen" if days else "Ø pro Tag",
                      _short_playtime(round(seconds / days)) if days else "—")

        for title, value in (
            ("Spielzeit", _short_playtime(seconds)),
            ("Starts", str(launches) if launches else "—"),
            ("Spiele", str(len(rows)) if rows else "—"),
            fourth,
        ):
            self.tiles.append(self._tile(title, value))

    def _tile(self, title: str, value: str) -> Gtk.Widget:
        caption = Gtk.Label(label=title, xalign=0.5)
        caption.add_css_class("stats-caption")
        number = Gtk.Label(label=value, xalign=0.5, wrap=True,
                           justify=Gtk.Justification.CENTER,
                           ellipsize=Pango.EllipsizeMode.END, max_width_chars=16)
        number.add_css_class("stats-value")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.add_css_class("stats-tile")
        box.append(number)
        box.append(caption)
        return box

    def _row(self, rank: int, game_id: str, entry: dict,
             top: dict) -> Gtk.ListBoxRow:
        game = self.library.games.get(game_id)

        place = Gtk.Label(label=f"{rank}", width_chars=2, xalign=1.0)
        place.add_css_class("stats-rank")

        title = Gtk.Label(label=self._name(game_id), xalign=0,
                          ellipsize=Pango.EllipsizeMode.END, hexpand=True)
        title.add_css_class("row-title")

        # The subtitle carries whatever the figure on the right does not, so
        # the same number never appears twice in one row.
        parts = []
        if self.metric == "playtime" and entry["launches"]:
            parts.append(f"{entry['launches']}× gestartet")
        if self.metric == "launches" and entry["seconds"]:
            parts.append(_short_playtime(entry["seconds"]) + " gespielt")
        if game is None:
            parts.append("nicht mehr in der Bibliothek")
        # Nothing to add rather than a dash: for "ever" the launch count is
        # often simply unknown, and a placeholder would read as "zero".
        subtitle = Gtk.Label(label="  ·  ".join(parts), xalign=0,
                             ellipsize=Pango.EllipsizeMode.END,
                             visible=bool(parts))
        subtitle.add_css_class("row-subtitle")

        key = "seconds" if self.metric == "playtime" else "launches"
        best = max(1, top[key])
        bar = Gtk.ProgressBar(fraction=min(1.0, entry[key] / best))
        bar.add_css_class("stats-bar")

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3,
                       hexpand=True, valign=Gtk.Align.CENTER)
        text.append(title)
        text.append(subtitle)
        text.append(bar)

        value = Gtk.Label(
            label=(_short_playtime(entry["seconds"]) if self.metric == "playtime"
                   else f"{entry['launches']}×"),
            xalign=1.0, valign=Gtk.Align.CENTER,
        )
        value.add_css_class("stats-figure")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                      margin_top=8, margin_bottom=8,
                      margin_start=12, margin_end=12)
        box.append(place)
        box.append(self._thumb(game))
        box.append(text)
        box.append(value)

        row = Gtk.ListBoxRow(child=box, activatable=game is not None)
        row.game_id = game_id if game is not None else ""
        return row

    def _thumb(self, game) -> Gtk.Widget:
        """The cover at row size, or its generated stand-in."""
        texture = (TEXTURES.get(game.cover_path, THUMB_W)
                   if game is not None and game.cover_path else None)
        if texture is not None:
            return Thumbnail(texture, THUMB_W, THUMB_H)

        name = game.name if game is not None else "?"
        label = Gtk.Label(label=initials(name))
        label.add_css_class("cover-initials")
        label.add_css_class("stats-initials")

        bin_ = Adw.Bin(child=label, width_request=THUMB_W,
                       height_request=THUMB_H, valign=Gtk.Align.CENTER)
        bin_.add_css_class("cover")
        bin_.add_css_class(placeholder_class(name))
        return bin_
