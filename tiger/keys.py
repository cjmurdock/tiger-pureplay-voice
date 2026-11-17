"""Send keystrokes to Pureplay with Windows SendInput (hardware scan codes, like JoyToKey)."""
import ctypes
import logging
import sys
import time

log = logging.getLogger("tiger.keys")

# name -> (scan code, extended)
SCAN = {
    **{c: (s, False) for c, s in zip("qwertyuiop", range(0x10, 0x1A))},
    **{c: (s, False) for c, s in zip("asdfghjkl", range(0x1E, 0x27))},
    **{c: (s, False) for c, s in zip("zxcvbnm", range(0x2C, 0x33))},
    **{f"f{n}": (0x3A + n, False) for n in range(1, 11)},
    "f11": (0x57, False), "f12": (0x58, False),
    "esc": (0x01, False), "escape": (0x01, False), "tab": (0x0F, False),
    "enter": (0x1C, False), "space": (0x39, False), "backspace": (0x0E, False),
    "ctrl": (0x1D, False), "control": (0x1D, False), "shift": (0x2A, False), "alt": (0x38, False),
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "num_minus": (0x4A, False), "num_plus": (0x4E, False),
    "insert": (0x52, True), "delete": (0x53, True), "home": (0x47, True), "end": (0x4F, True),
    "pageup": (0x49, True), "pagedown": (0x51, True),
}
for n in range(10):  # fix digits: 1..9 -> 0x02..0x0A, 0 -> 0x0B
    SCAN[str(n)] = ((0x01 + n) if n else 0x0B, False)


def parse_combo(combo):
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    for p in parts:
        if p not in SCAN:
            raise ValueError(f"Unknown key '{p}' in '{combo}'")
    return parts


IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    INPUT_KEYBOARD = 1
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _key_event(name, up):
        scan, ext = SCAN[name]
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0) | (KEYEVENTF_KEYUP if up else 0)
        inp = INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)))
        if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
            log.warning("SendInput failed for %s (error %s)", name, ctypes.get_last_error())

    def list_windows():
        titles = []

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    titles.append((hwnd, buf.value))
            return True
        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return titles

    def find_window(title_part):
        title_part = title_part.lower()
        for hwnd, title in list_windows():
            t = title.lower()
            if title_part in t and "tiger" not in t and "launcher" not in t:
                return hwnd
        return None

    def focus_window(title_part):
        hwnd = find_window(title_part)
        if not hwnd:
            log.debug("No window matching '%s'", title_part)
            return False
        if user32.GetForegroundWindow() == hwnd:
            return True
        # Tapping Alt lets a background process take the foreground on most Windows builds.
        _key_event("alt", False)
        _key_event("alt", True)
        ok = bool(user32.SetForegroundWindow(hwnd))
        time.sleep(0.05)
        return ok
else:
    def _key_event(name, up):
        log.info("[not Windows] key %s %s", name, "up" if up else "down")

    def list_windows():
        return []

    def find_window(title_part):
        return None

    def focus_window(title_part):
        return False


def press(combo, hold=0.06, dry_run=False):
    keys = parse_combo(combo)
    if dry_run:
        log.info("[dry run] would press %s", combo)
        return
    for k in keys:
        _key_event(k, up=False)
        time.sleep(0.02)
    time.sleep(hold)
    for k in reversed(keys):
        _key_event(k, up=True)
        time.sleep(0.02)
