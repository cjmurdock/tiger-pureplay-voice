"""Update Tiger to the latest version on GitHub, keeping the person's own settings.

Run by update.bat (python tiger.py --update). It:
  1. checks GitHub for the latest version and stops if this copy is already current,
  2. asks you to close Tiger if it's running (and offers to start it again afterwards),
  3. backs up the current program files to backups\\,
  4. copies the new files in, never touching config.json, token.json or the speech model,
  5. adds any brand-new settings to config.json (with their default values) without
     changing anything already there,
  6. reinstalls Python packages only if requirements.txt changed.
"""
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
import zipfile

from . import config_store

REPO = "cjmurdock/tiger-pureplay-voice"
BRANCH = "main"
ZIP_URL = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
COMMIT_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
VERSION_FILE = "version.json"

# Never overwritten: the person's own settings, pairing and local files.
KEEP = {"config.json", "token.json", "status.json", "tiger_request.json", "config.backup.json",
        VERSION_FILE}
KEEP_DIRS = {"models", "backups", ".git"}
# Settings where a missing entry is a choice (e.g. a club taken out of the bag), so new
# defaults are never added inside them.
NO_MERGE = {"carry_yards"}
MAX_BACKUPS = 3


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Tiger-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_commit():
    """{'sha', 'date', 'message'} for the newest version on GitHub, or None if unreachable."""
    try:
        data = json.loads(_get(COMMIT_URL, timeout=15))
        c = data["commit"]
        return {"sha": data["sha"], "date": c["committer"]["date"][:10],
                "message": c["message"].splitlines()[0]}
    except Exception:
        return None


def installed_version(base_dir):
    try:
        with open(os.path.join(base_dir, VERSION_FILE), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _is_kept(rel):
    parts = rel.replace("\\", "/").split("/")
    return parts[0] in KEEP_DIRS or (len(parts) == 1 and parts[0] in KEEP) or \
        parts[-1].endswith("_log.txt") or "__pycache__" in parts


def _zip_members(zf):
    """(relative path, ZipInfo) for every file, with GitHub's top folder stripped."""
    names = [n for n in zf.namelist() if not n.endswith("/")]
    top = os.path.commonprefix([n.split("/", 1)[0] + "/" for n in names]) if names else ""
    for info in zf.infolist():
        if info.is_dir():
            continue
        rel = info.filename[len(top):] if top and info.filename.startswith(top) else info.filename
        if rel and ".." not in rel.split("/") and not rel.startswith("/"):
            yield rel, info


def backup(base_dir, rels):
    """Zip the current copies of the files about to be replaced into backups\\."""
    bdir = os.path.join(base_dir, "backups")
    os.makedirs(bdir, exist_ok=True)
    path = os.path.join(bdir, time.strftime("tiger-before-update-%Y%m%d-%H%M%S.zip"))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in rels:
            src = os.path.join(base_dir, rel)
            if os.path.isfile(src):
                z.write(src, rel)
        cfg = os.path.join(base_dir, "config.json")
        if os.path.isfile(cfg):
            z.write(cfg, "config.json")
    old = sorted(f for f in os.listdir(bdir) if f.startswith("tiger-before-update-"))
    for f in old[:-MAX_BACKUPS]:
        try:
            os.remove(os.path.join(bdir, f))
        except OSError:
            pass
    return path


def missing_settings(current, defaults, prefix=""):
    """{"dotted.path": default} for settings in defaults that current doesn't have."""
    out = {}
    for key, val in defaults.items():
        path = f"{prefix}{key}"
        if key not in current:
            out[path] = val
        elif isinstance(val, dict) and isinstance(current[key], dict) and path not in NO_MERGE:
            out.update(missing_settings(current[key], val, path + "."))
    return out


def tiger_running(base_dir):
    try:
        return config_store.tiger_is_running(base_dir)
    except Exception:
        return False


def _ask(prompt, default=True):
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return default
    return default if not ans else ans.startswith("y")


def apply_update(base_dir, zip_bytes, say=print):
    """Install the files from a GitHub ZIP into base_dir. Returns a summary dict."""
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    members = [(rel, info) for rel, info in _zip_members(zf) if not _is_kept(rel)]
    if not any(rel == "tiger.py" for rel, _ in members):
        raise RuntimeError("The download doesn't look like Tiger (no tiger.py in it).")

    old_reqs = _read(os.path.join(base_dir, "requirements.txt"))
    changed = [rel for rel, info in members if _read_bytes(os.path.join(base_dir, rel)) != zf.read(info)]
    summary = {"changed": changed, "backup": None, "new_settings": [], "packages": False}
    if changed:
        summary["backup"] = backup(base_dir, changed)
        for rel in changed:
            dest = os.path.join(base_dir, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = dest + ".new"
            with open(tmp, "wb") as f:
                f.write(zf.read(next(i for r, i in members if r == rel)))
            os.replace(tmp, dest)

    # New settings: add them with their defaults, leave everything else alone.
    default_cfg = next((zf.read(i) for r, i in _zip_members(zf) if r == "config.json"), None)
    cfg_path = config_store.config_path(base_dir)
    if default_cfg is not None:
        defaults = json.loads(default_cfg.decode("utf-8-sig"))
        if not os.path.exists(cfg_path):
            with open(cfg_path, "wb") as f:
                f.write(default_cfg)
            summary["new_settings"] = ["(created config.json with the default settings)"]
        else:
            try:
                current = config_store.load_config(base_dir)
                extra = missing_settings(current, defaults)
                if extra:
                    config_store.update_config(base_dir, extra)
                summary["new_settings"] = sorted(extra)
            except config_store.ConfigError as e:
                say(f"Couldn't add new settings: {e}")

    if _read(os.path.join(base_dir, "requirements.txt")) != old_reqs:
        summary["packages"] = True
    return summary


def save_version(base_dir, latest):
    with open(os.path.join(base_dir, VERSION_FILE), "w", encoding="utf-8") as f:
        json.dump(dict(latest, installed=time.strftime("%Y-%m-%d %H:%M")), f, indent=2)


def is_current(base_dir, latest):
    mine = installed_version(base_dir)
    return bool(latest and mine and mine.get("sha") == latest["sha"])


def download_and_install(base_dir, latest=None, say=print):
    """Download main from GitHub and install it. Installs Python packages if needed."""
    data = _get(ZIP_URL, timeout=120)
    summary = apply_update(base_dir, data, say=say)
    if latest:
        save_version(base_dir, latest)
    if summary["packages"]:
        flags = 0x08000000 if sys.platform == "win32" else 0       # CREATE_NO_WINDOW
        python = sys.executable
        if python.lower().endswith("pythonw.exe"):
            python = python[:-len("pythonw.exe")] + "python.exe"
        summary["packages_ok"] = subprocess.call(
            [python, "-m", "pip", "install", "-r", os.path.join(base_dir, "requirements.txt")],
            creationflags=flags) == 0
    return summary


def _read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _read(path):
    b = _read_bytes(path)
    return b.decode("utf-8", "replace") if b is not None else None


def _is_tiger(path):
    return bool(path) and os.path.isfile(os.path.join(path, "tiger.py")) and \
        os.path.isfile(os.path.join(path, "tiger", "app.py"))


def find_tiger_folders(hints=(), skip=()):
    """Tiger installs on this PC, real installs (with the speech model) first."""
    home = os.path.expanduser("~")
    places = [h for h in hints if h] + [r"C:\Tiger", r"D:\Tiger"] + \
        [os.path.join(home, *p) for p in (("Tiger",), ("Desktop", "Tiger"), ("Documents", "Tiger"),
                                           ("OneDrive", "Desktop", "Tiger"),
                                           ("OneDrive", "Documents", "Tiger"))]
    skip = {os.path.normcase(os.path.abspath(s)) for s in skip if s}
    found = []

    def add(p):
        p = os.path.abspath(p)
        key = os.path.normcase(p)
        if _is_tiger(p) and key not in skip and key not in {os.path.normcase(f) for f in found}:
            found.append(p)

    for p in places:
        add(p)
    if not any(os.path.isdir(os.path.join(f, "models")) for f in found):
        # No set-up Tiger in the usual places: look a few folders deep in the user's folders and at the top of each drive.
        roots = [(home, 4)]
        if sys.platform == "win32":
            import string
            roots += [(f"{d}:\\", 2) for d in string.ascii_uppercase if os.path.isdir(f"{d}:\\")]
        for root, depth in roots:
            base_depth = root.rstrip("\\/").count(os.sep)
            for dirpath, dirnames, filenames in os.walk(root):
                if dirpath.rstrip("\\/").count(os.sep) - base_depth >= depth:
                    dirnames[:] = []
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in
                               ("windows", "program files", "program files (x86)", "programdata",
                                "appdata", "$recycle.bin", "node_modules", "__pycache__")]
                if "tiger.py" in filenames:
                    add(dirpath)
    found.sort(key=lambda p: not os.path.isdir(os.path.join(p, "models")))
    return found


def choose_tiger_folder(hints=(), skip=()):
    print("Looking for your Tiger folder...")
    found = find_tiger_folders(hints, skip)
    if len(found) == 1:
        if _ask(f"Update the Tiger in {found[0]}? [Y/n] "):
            return found[0]
    elif found:
        print("Found more than one Tiger folder:")
        for i, p in enumerate(found, 1):
            note = "" if os.path.isdir(os.path.join(p, "models")) else "   (not set up)"
            print(f"  {i}. {p}{note}")
        ans = input("Which one do you use? Type its number: ").strip()
        if ans.isdigit() and 1 <= int(ans) <= len(found):
            return found[int(ans) - 1]
    try:
        ans = input("Type or paste the path of your Tiger folder (the one with tiger.py in it): ")
    except EOFError:
        return None
    ans = ans.strip().strip('"')
    return os.path.abspath(ans) if _is_tiger(ans) else None


def close_tiger(base_dir, timeout=10):
    """Ask a running Tiger to close. Newer versions obey a request from this folder; older ones
    (before the Updates tab) are closed by their window title. Returns True once it's closed."""
    try:
        config_store.send_request(base_dir, "quit")
    except OSError:
        pass
    end = time.time() + timeout / 2
    while time.time() < end:
        if not tiger_running(base_dir):
            return True
        time.sleep(0.5)
    if sys.platform == "win32":
        for title in ("Tiger Voice Control*", "Tiger"):
            subprocess.call(["taskkill", "/FI", f"WINDOWTITLE eq {title}", "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
            if not tiger_running(base_dir):
                return True
    end = time.time() + timeout / 2
    while time.time() < end:
        if not tiger_running(base_dir):
            return True
        time.sleep(0.5)
    return False


def run(base_dir, zip_path=None, assume_yes=False):
    print("Tiger updater")
    print("=============")
    print(f"Tiger folder: {base_dir}\n")
    if not os.path.isfile(os.path.join(base_dir, "tiger.py")):
        print("That folder doesn't have Tiger in it (no tiger.py). Nothing was changed.")
        return 1

    latest = latest_commit()
    if latest:
        print(f"Latest version on GitHub: {latest['date']}  {latest['message']}")
        if is_current(base_dir, latest):
            print("\nYou already have the latest version. Nothing to do.")
            return 0
    elif not zip_path:
        print("Couldn't check GitHub for the latest version; downloading it anyway.")

    was_running = tiger_running(base_dir)
    if was_running:
        print("\nTiger is running, so it needs to close for the update.")
        if assume_yes or _ask("Close Tiger now? It will be started again afterwards. [Y/n] "):
            print("Closing Tiger...")
            close_tiger(base_dir)
        if tiger_running(base_dir):
            print("Please close Tiger's window (titled \"Tiger Voice Control\"); this will carry on")
            print("by itself. Press Ctrl+C to cancel.")
            try:
                while tiger_running(base_dir):
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nCancelled. Nothing was changed.")
                return 1
        time.sleep(1)
        print("Tiger is closed.")

    try:
        if zip_path:
            with open(zip_path, "rb") as f:
                summary = apply_update(base_dir, f.read())
            if latest:
                save_version(base_dir, latest)
            if summary["packages"]:
                flags = 0x08000000 if sys.platform == "win32" else 0
                summary["packages_ok"] = subprocess.call(
                    [sys.executable, "-m", "pip", "install", "-r",
                     os.path.join(base_dir, "requirements.txt")], creationflags=flags) == 0
        else:
            print("\nDownloading the latest version...")
            summary = download_and_install(base_dir, latest)
    except Exception as e:
        print(f"\nThe update didn't work: {e}")
        print("Nothing important was lost: your settings and pairing aren't touched, and any files")
        print("that were replaced are in the backups folder.")
        return 1

    print()
    if summary["changed"]:
        print(f"Updated {len(summary['changed'])} file(s):")
        for rel in summary["changed"]:
            print(f"  {rel}")
        print(f"The old copies are saved in {os.path.relpath(summary['backup'], base_dir)}")
    else:
        print("Your program files were already up to date.")
    if summary["new_settings"]:
        print("New settings added to config.json (your existing settings weren't changed):")
        for s in summary["new_settings"]:
            print(f"  {s}")
    print("Kept as they were: config.json settings, token.json (your Pureplay pairing), the speech model.")

    if summary["packages"]:
        print("\nThis version needed updated Python packages: " +
              ("installed." if summary.get("packages_ok") else
               "that didn't work. Run setup.bat to install them."))

    print("\nUpdate finished.")
    if was_running and (assume_yes or _ask("Start Tiger again now? [Y/n] ")):
        bat = os.path.join(base_dir, "run_tiger.bat")
        if sys.platform == "win32" and os.path.exists(bat):
            subprocess.Popen(["cmd", "/c", "start", "Tiger", "/min", bat], cwd=base_dir)
            print("Tiger is starting (minimized).")
    return 0
