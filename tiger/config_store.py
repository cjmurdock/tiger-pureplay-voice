"""Reading and safely saving config.json, plus the small files Tiger shares with the
Settings window (status.json and tiger_request.json).

Saving is shared by the Settings window and Tiger's own voice commands, so it:
  * re-reads the file and changes only the settings it was asked to change,
  * keeps the previous version as config.backup.json,
  * writes to a temporary file first and then swaps it in, so a crash or power cut never
    leaves a half-written config.json behind.

Pure Python with no Windows dependencies, so it can be tested anywhere.
"""
import json
import os
import time

CONFIG = "config.json"
BACKUP = "config.backup.json"
STATUS = "status.json"
REQUEST = "tiger_request.json"

DELETE = object()   # pass as a value to update_config() to remove that setting


class ConfigError(Exception):
    pass


def config_path(base_dir):
    return os.path.join(base_dir, CONFIG)


def _parse(text, name=CONFIG):
    try:
        cfg = json.loads(text)
    except ValueError as e:
        line = getattr(e, "lineno", None)
        where = f" on line {line}" if line else ""
        raise ConfigError(f"{name} has a mistake{where} ({getattr(e, 'msg', e)}). "
                          f"Fix it, or copy {BACKUP} over it.") from None
    if not isinstance(cfg, dict):
        raise ConfigError(f"{name} should start with {{ and end with }}.")
    return cfg


def load_config(base_dir):
    path = config_path(base_dir)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        raise ConfigError(f"Can't read {path}: {e}") from None
    return _parse(text)


def config_mtime(base_dir):
    try:
        return os.stat(config_path(base_dir)).st_mtime_ns
    except OSError:
        return None


def get(cfg, path, default=None):
    """get(cfg, "voice.name") -> value, or default if any part is missing."""
    cur = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _set(cfg, path, value):
    parts = path.split(".")
    cur = cfg
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    if value is DELETE:
        cur.pop(parts[-1], None)
    else:
        cur[parts[-1]] = value


def _write_atomic(path, text):
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    # On Windows the swap can fail for a moment if another program is reading the file.
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(0.05)


def update_config(base_dir, changes):
    """Apply {"voice.name": "Linda", "carry_yards.Iron7": 160, ...} to config.json.

    Everything else in the file is kept as it is. Returns the new config dict.
    Raises ConfigError (and writes nothing) if the current file can't be read.
    """
    path = config_path(base_dir)
    with open(path, "r", encoding="utf-8-sig") as f:
        old_text = f.read()
    cfg = _parse(old_text)
    for key, value in changes.items():
        _set(cfg, key, value)
    new_text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    if new_text == old_text:
        return cfg
    try:
        _write_atomic(os.path.join(base_dir, BACKUP), old_text)
    except OSError:
        pass   # a missing backup shouldn't stop the save
    _write_atomic(path, new_text)
    return cfg


# ---------- status.json (written by Tiger, read by the Settings window) ----------
def write_status(base_dir, status):
    status = dict(status, updated=time.time(), pid=os.getpid())
    try:
        _write_atomic(os.path.join(base_dir, STATUS), json.dumps(status, indent=2))
    except OSError:
        pass


def read_status(base_dir):
    try:
        with open(os.path.join(base_dir, STATUS), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------- tiger_request.json (written by the Settings window, handled by Tiger) ----------
def send_request(base_dir, action, **data):
    _write_atomic(os.path.join(base_dir, REQUEST), json.dumps(dict(data, action=action)))


def take_request(base_dir):
    """Return and remove a pending request from the Settings window, or None."""
    path = os.path.join(base_dir, REQUEST)
    try:
        with open(path, "r", encoding="utf-8") as f:
            req = json.load(f)
    except (OSError, ValueError):
        return None
    try:
        os.remove(path)
    except OSError:
        pass
    return req if isinstance(req, dict) else None
