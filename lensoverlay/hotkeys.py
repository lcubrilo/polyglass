"""System-wide hotkeys via the Win32 RegisterHotKey API, on a thread with its own message loop."""
import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MODIFIERS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
SPECIAL_KEYS = {"space": 0x20, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "`": 0xC0, "backtick": 0xC0}


def parse(combo: str) -> tuple[int, int]:
    *mods, key = [part.strip().lower() for part in combo.split("+")]
    modifiers = MOD_NOREPEAT
    for mod in mods:
        if mod not in MODIFIERS:
            raise ValueError(f"Unknown modifier '{mod}' in hotkey '{combo}'")
        modifiers |= MODIFIERS[mod]
    if key in SPECIAL_KEYS:
        vk = SPECIAL_KEYS[key]
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit():
        vk = 0x6F + int(key[1:])
    else:
        raise ValueError(f"Unsupported key '{key}' in hotkey '{combo}'")
    return modifiers, vk


class HotkeyListener(threading.Thread):
    def __init__(self, bindings: dict[str, callable]):
        super().__init__(daemon=True, name="hotkeys")
        self._bindings = list(bindings.items())
        self._thread_id = None
        self.failed: list[str] = []
        self._ready = threading.Event()

    def run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        for idx, (combo, _) in enumerate(self._bindings, start=1):
            mods, vk = parse(combo)
            if not user32.RegisterHotKey(None, idx, mods, vk):
                self.failed.append(combo)
        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and 1 <= msg.wParam <= len(self._bindings):
                self._bindings[msg.wParam - 1][1]()
        for idx in range(1, len(self._bindings) + 1):
            user32.UnregisterHotKey(None, idx)

    def wait_ready(self):
        self._ready.wait(2)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
