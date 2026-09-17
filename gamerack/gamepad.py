"""Gamepad input, read straight from the kernel's joystick devices.

No extra dependency and no library: `/dev/input/js*` hands out fixed 8-byte
records, and two ioctls tell us which physical button each index stands for, so
we do not have to guess at numbering that differs between an Xbox pad, a
DualSense and an 8BitDo in whichever mode it happens to be in.

Devices are polled for every couple of seconds, so a pad that is switched on
after Gamerack started is picked up without a restart.
"""

from __future__ import annotations

import fcntl
import glob
import logging
import os
import struct

from gi.repository import GLib

log = logging.getLogger(__name__)

JS_EVENT = struct.Struct("IhBB")      # time, value, type, number
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80                  # synthetic event describing the initial state

# ioctls from linux/joystick.h. _IOR(type, nr, size) = 2<<30 | size<<16 | ...
JSIOCGAXES = 0x80000000 | (1 << 16) | (ord("j") << 8) | 0x11       # __u8
JSIOCGBUTTONS = 0x80000000 | (1 << 16) | (ord("j") << 8) | 0x12    # __u8
JSIOCGNAME = 0x80000000 | (128 << 16) | (ord("j") << 8) | 0x13     # char[128]
JSIOCGAXMAP = 0x80000000 | (64 << 16) | (ord("j") << 8) | 0x32     # __u8[ABS_CNT]
JSIOCGBTNMAP = 0x80000000 | (1024 << 16) | (ord("j") << 8) | 0x34  # __u16[512]

# Kernel key codes, in the terms this program thinks in.
KEY_ACTIONS = {
    0x130: "a",        # BTN_SOUTH / BTN_A — confirm
    0x131: "b",        # BTN_EAST / BTN_B  — back
    0x133: "x",
    0x134: "y",
    0x13A: "select",
    0x13B: "start",
    0x13C: "guide",
}

# Absolute axes: the d-pad hat first, then the left stick.
AXIS_DIRECTIONS = {
    0x10: ("left", "right"),   # ABS_HAT0X
    0x11: ("up", "down"),      # ABS_HAT0Y
    0x00: ("left", "right"),   # ABS_X
    0x01: ("up", "down"),      # ABS_Y
}

# Fallback when the ioctls are unavailable: the numbering almost every pad uses.
FALLBACK_BUTTONS = {0: "a", 1: "b", 2: "x", 3: "y", 6: "select", 7: "start",
                    8: "guide"}
FALLBACK_AXES = {0: 0x00, 1: 0x01, 6: 0x10, 7: 0x11}

# Joystick axes are normalised to +-32767 whatever the hardware reports. The gap
# between the two thresholds keeps a stick resting near the edge from chattering.
PRESS = 20000
RELEASE = 12000

FIRST_REPEAT = 400                     # ms before a held direction repeats
NEXT_REPEAT = 110


class _Device:
    """One open joystick device and what its numbered inputs mean."""

    def __init__(self, path: str, fd: int):
        self.path = path
        self.fd = fd
        self.watch = 0
        self.buttons = self._button_map()
        self.axes = self._axis_map()
        self.name = self._name()
        self.pressed: dict[int, str] = {}   # axis number -> direction now held

    def _name(self) -> str:
        try:
            raw = fcntl.ioctl(self.fd, JSIOCGNAME, bytes(128))
        except (OSError, OverflowError, ValueError):
            return self.path
        return raw.split(b"\0")[0].decode("utf-8", "replace") or self.path

    def _count(self, request: int) -> int:
        try:
            return fcntl.ioctl(self.fd, request, bytes(1))[0]
        except (OSError, OverflowError, ValueError):
            return 0

    def _button_map(self) -> dict[int, str]:
        count = self._count(JSIOCGBUTTONS)
        try:
            raw = fcntl.ioctl(self.fd, JSIOCGBTNMAP, bytes(1024))
        except (OSError, OverflowError, ValueError):
            return dict(FALLBACK_BUTTONS)
        codes = struct.unpack("512H", raw)[:count or 512]
        mapping = {index: KEY_ACTIONS[code]
                   for index, code in enumerate(codes) if code in KEY_ACTIONS}
        return mapping or dict(FALLBACK_BUTTONS)

    def _axis_map(self) -> dict[int, tuple[str, str]]:
        fallback = {index: AXIS_DIRECTIONS[code]
                    for index, code in FALLBACK_AXES.items()}
        # The map is always ABS_CNT entries long; everything past the axes this
        # device actually has is zero, which would otherwise read as ABS_X.
        count = self._count(JSIOCGAXES)
        if not count:
            return fallback
        try:
            raw = fcntl.ioctl(self.fd, JSIOCGAXMAP, bytes(64))
        except (OSError, OverflowError, ValueError):
            return fallback
        mapping = {index: AXIS_DIRECTIONS[code]
                   for index, code in enumerate(raw[:count])
                   if code in AXIS_DIRECTIONS}
        return mapping or fallback


class Gamepads:
    """Watches every connected pad and reports actions on the main loop.

    `on_action(name)` gets "left", "right", "up", "down", "a", "b", "x", "y",
    "start", "select" or "guide". Directions repeat while they are held.
    """

    def __init__(self, on_action):
        self._on_action = on_action
        self.devices: dict[str, _Device] = {}
        self.failed: set[str] = set()
        # Kept so the preferences dialog can show what is arriving; a controller
        # that does nothing is otherwise impossible to tell apart from one that
        # is not being read at all.
        self.last_action = ""
        self.last_device = ""
        self._held = ""
        self._held_device = ""
        self._repeat = 0
        self._scan = GLib.timeout_add_seconds(2, self._poll)
        self._poll()

    def on_action(self, action: str, device: str = "") -> None:
        self.last_action = action
        if device:
            self.last_device = device
        log.info("Gamepad: %s", action)
        self._on_action(action)

    def names(self) -> list[str]:
        return [d.name for d in self.devices.values() if d.fd >= 0]

    # --- devices ------------------------------------------------------------

    def _poll(self) -> bool:
        present = set(glob.glob("/dev/input/js*"))
        self.failed &= present            # unplugged: worth another try later
        for path in sorted(present):
            if path not in self.devices and path not in self.failed:
                self._open(path)
        return True

    def _open(self, path: str) -> None:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as error:
            # Usually a permission problem. Remember the failure so the two-second
            # poll does not log the same complaint forever.
            log.info("Gamepad %s nicht lesbar: %s", path, error)
            self.failed.add(path)
            return
        device = _Device(path, fd)
        device.watch = GLib.unix_fd_add_full(
            GLib.PRIORITY_DEFAULT, fd,
            GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
            self._on_readable, path,
        )
        self.devices[path] = device
        log.info("Gamepad angeschlossen: %s", path)

    def _close(self, path: str) -> None:
        device = self.devices.pop(path, None)
        if device is None:
            return
        if device.watch:
            GLib.source_remove(device.watch)
        if device.fd >= 0:
            try:
                os.close(device.fd)
            except OSError:
                pass
        if self._held:
            self._direction(None)

    # --- reading ------------------------------------------------------------

    def _on_readable(self, fd: int, condition, path: str) -> bool:
        device = self.devices.get(path)
        if device is None:
            return False
        if condition & (GLib.IOCondition.HUP | GLib.IOCondition.ERR):
            self._close(path)
            return False
        try:
            data = os.read(fd, JS_EVENT.size * 32)
        except BlockingIOError:
            return True
        except OSError:
            self._close(path)
            return False
        if not data:
            self._close(path)
            return False

        for offset in range(0, len(data) - JS_EVENT.size + 1, JS_EVENT.size):
            _time, value, kind, number = JS_EVENT.unpack_from(data, offset)
            # The kernel replays the current state when the device is opened;
            # acting on that would move the selection the moment a pad is
            # plugged in.
            if kind & JS_EVENT_INIT:
                continue
            if kind == JS_EVENT_BUTTON:
                self._on_button(device, number, value)
            elif kind == JS_EVENT_AXIS:
                self._on_axis(device, number, value)
        return True

    def _on_button(self, device: _Device, number: int, value: int) -> None:
        if not value:                       # only act on press, not release
            return
        action = device.buttons.get(number)
        if action:
            self.on_action(action, device.name)
        else:
            log.debug("Gamepad: Taste %d ohne Zuordnung", number)

    def _on_axis(self, device: _Device, number: int, value: int) -> None:
        directions = device.axes.get(number)
        if directions is None:
            return
        negative, positive = directions
        held = device.pressed.get(number)

        if value <= -PRESS:
            wanted = negative
        elif value >= PRESS:
            wanted = positive
        elif abs(value) <= RELEASE:
            wanted = None
        else:
            return                          # in between: leave things as they are

        if wanted == held:
            return
        device.pressed[number] = wanted
        if wanted:
            self._direction(wanted, device.name)
        elif self._held == held:
            self._direction(None)

    # --- auto-repeat --------------------------------------------------------

    def _direction(self, name: str | None, device: str = "") -> None:
        if name == (self._held or None):
            return
        self._held = name or ""
        self._held_device = device
        if self._repeat:
            GLib.source_remove(self._repeat)
            self._repeat = 0
        if name:
            self.on_action(name, device)
            self._repeat = GLib.timeout_add(FIRST_REPEAT, self._tick)

    def _tick(self) -> bool:
        if not self._held:
            self._repeat = 0
            return False
        self.on_action(self._held, self._held_device)
        self._repeat = GLib.timeout_add(NEXT_REPEAT, self._tick)
        return False

    # --- teardown -----------------------------------------------------------

    def stop(self) -> None:
        if self._scan:
            GLib.source_remove(self._scan)
            self._scan = 0
        for path in list(self.devices):
            self._close(path)
