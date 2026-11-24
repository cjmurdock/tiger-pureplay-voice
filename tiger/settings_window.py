"""Tiger Settings: a small window for the settings people usually change.

    Voice        pick a voice, hear a preview, set speed and volume
    Microphone   pick the mic, watch a live level meter, set how sure Tiger must be
    Distances    your carry distance for each club
    Status       is Tiger running, is it paired with Pureplay (and how), re-pair

    Updates      check GitHub for a new version and install it in one click

Start it with "Tiger Settings.bat" or "python tiger.py --settings". Changes are saved to
config.json straight away (keeping everything else in the file), and a running Tiger picks
them up within a second, so there's no need to restart it.
"""
import array
import math
import os
import queue
import subprocess
import threading
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import config_store
from .config_store import ConfigError, get, tiger_is_running

PREVIEW_TEXT = "You're up. One fifty to the pin."

# Clubs shown on the Distances tab, longest first (Accessory API club types).
CLUB_ORDER = (["Driver", "Wood3", "Wood4", "Wood5", "Wood7", "Wood9",
               "Hybrid2", "Hybrid3", "Hybrid4", "Hybrid5", "Hybrid6"] +
              [f"Iron{n}" for n in range(2, 10)] +
              ["PitchingWedge", "GapWedge", "SandWedge", "LobWedge"])


def club_label(club_type):
    from .commands import club_spoken
    return club_spoken(club_type).capitalize()


class SettingsWindow:
    def __init__(self, root, base_dir):
        self.root = root
        self.base_dir = base_dir
        self.cfg = {}
        self.cfg_error = None
        self._cfg_mtime = None
        self._save_jobs = {}
        self._preview = None              # Speaker used for previews (created on first use)
        self.voices = []
        self.mic_stream = None
        self.mic_level = 0.0
        self.mic_devices = []
        self._ui = queue.Queue()          # work from background threads, run on the UI thread
        self.latest = None
        self.updating = False

        root.title("Tiger Settings")
        root.minsize(640, 520)
        self.load_config()

        style = ttk.Style()
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Good.TLabel", foreground="#1a7f37")
        style.configure("Bad.TLabel", foreground="#b42318")
        style.configure("Big.TLabel", font=("Segoe UI", 11, "bold"))

        self.banner = ttk.Label(root, style="Bad.TLabel", wraplength=600, padding=(12, 8, 12, 0))
        self.banner.pack(fill="x")
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.build_voice_tab()
        self.build_mic_tab()
        self.build_distance_tab()
        self.build_status_tab()
        self.build_update_tab()
        self.saved_label = ttk.Label(root, style="Hint.TLabel", padding=(12, 0, 12, 10))
        self.saved_label.pack(fill="x")

        self.nb.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_config_error()
        self.root.after(500, self.tick)

    # ------------------------------------------------------------------ config
    def load_config(self):
        try:
            self.cfg = config_store.load_config(self.base_dir)
            self.cfg_error = None
        except ConfigError as e:
            self.cfg_error = str(e)
        self._cfg_mtime = config_store.config_mtime(self.base_dir)

    def show_config_error(self):
        if self.cfg_error:
            self.banner.configure(text=f"{self.cfg_error}  Settings can't be saved until it's fixed.")
        else:
            self.banner.configure(text="")

    def save(self, changes, what="Saved"):
        try:
            self.cfg = config_store.update_config(self.base_dir, changes)
            self.cfg_error = None
        except (ConfigError, OSError) as e:
            self.cfg_error = str(e)
            self.show_config_error()
            return False
        self._cfg_mtime = config_store.config_mtime(self.base_dir)
        self.show_config_error()
        when = ("Tiger is using it now." if tiger_is_running(self.base_dir)
                else "Tiger will use it the next time it starts.")
        self.saved_label.configure(text=f"{what}. {when}")
        return True

    def save_later(self, key, changes, what, delay=600):
        """Save after a slider stops moving, rather than on every pixel."""
        pending = self._save_jobs.pop(key, None)
        if pending:
            self.root.after_cancel(pending[0])

        def run():
            self._save_jobs.pop(key, None)
            self.save(changes(), what)
        self._save_jobs[key] = (self.root.after(delay, run), run)

    # ------------------------------------------------------------------ voice tab
    def build_voice_tab(self):
        from .audio import rate_to_step, RATE_MIN_STEP, RATE_MAX_STEP
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="Voice")
        ttk.Label(tab, text="Pick the voice Tiger talks with. Double-click one, or press Preview, "
                            "to hear it.", style="Hint.TLabel").pack(anchor="w")

        lf = ttk.Frame(tab)
        lf.pack(fill="both", expand=True, pady=(8, 8))
        self.voice_tree = ttk.Treeview(lf, columns=("lang", "gender", "use"), height=8,
                                       selectmode="browse")
        self.voice_tree.heading("#0", text="Voice")
        self.voice_tree.heading("lang", text="Language")
        self.voice_tree.heading("gender", text="")
        self.voice_tree.heading("use", text="")
        self.voice_tree.column("#0", width=150)
        self.voice_tree.column("lang", width=200)
        self.voice_tree.column("gender", width=80)
        self.voice_tree.column("use", width=110)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.voice_tree.yview)
        self.voice_tree.configure(yscrollcommand=sb.set)
        self.voice_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.voice_tree.bind("<Double-1>", lambda e: self.preview())

        sliders = ttk.Frame(tab)
        sliders.pack(fill="x")
        sliders.columnconfigure(1, weight=1)
        v = self.cfg.get("voice", {})
        ttk.Label(sliders, text="Speed").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.rate_var = tk.IntVar(value=rate_to_step(v.get("rate", 190)))
        ttk.Scale(sliders, from_=RATE_MIN_STEP, to=RATE_MAX_STEP, variable=self.rate_var,
                  command=lambda _: self.on_rate()).grid(row=0, column=1, sticky="ew")
        self.rate_label = ttk.Label(sliders, width=12)
        self.rate_label.grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Label(sliders, text="Volume").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(6, 0))
        self.vol_var = tk.IntVar(value=int(round(float(v.get("volume", 1.0)) * 100)))
        ttk.Scale(sliders, from_=10, to=100, variable=self.vol_var,
                  command=lambda _: self.on_volume()).grid(row=1, column=1, sticky="ew", pady=(6, 0))
        self.vol_label = ttk.Label(sliders, width=12)
        self.vol_label.grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(6, 0))
        self.update_slider_labels()

        pv = ttk.Frame(tab)
        pv.pack(fill="x", pady=(12, 0))
        ttk.Label(pv, text="Preview line").pack(side="left", padx=(0, 10))
        self.preview_var = tk.StringVar(value=PREVIEW_TEXT)
        ttk.Entry(pv, textvariable=self.preview_var).pack(side="left", fill="x", expand=True)

        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Preview", command=self.preview).pack(side="left")
        ttk.Button(btns, text="Stop", command=self.stop_preview).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="Use this voice", command=self.use_voice).pack(side="right")
        ttk.Button(btns, text="Use the Windows default",
                   command=self.use_default_voice).pack(side="right", padx=(0, 6))
        self.load_voices()

    def load_voices(self):
        try:
            from .audio import voice_info
            self.voices = voice_info()
        except Exception as e:
            self.voices = []
            self.voice_tree.insert("", "end", text="(can't list voices)", values=(str(e)[:60], "", ""))
            return
        for v in self.voices:
            self.voice_tree.insert("", "end", iid=v["description"], text=v["name"],
                                   values=(v["language"], v["gender"], ""))
        self.mark_voice_in_use(select=True)

    def voice_in_use(self):
        """The voice Tiger uses: what a running Tiger reports, otherwise what config.json says."""
        st = config_store.read_status(self.base_dir)
        if st and st.get("running") and st.get("voice") and tiger_is_running(self.base_dir) \
                and st.get("voice_setting") == get(self.cfg, "voice.name"):
            return st["voice"]
        want = (get(self.cfg, "voice.name") or "").lower().strip()
        if not want:
            return None
        for v in self.voices:
            if v["name"].lower() == want or v["description"].lower() == want:
                return v["description"]
        for v in self.voices:
            if want in v["description"].lower():
                return v["description"]
        return None

    def mark_voice_in_use(self, select=False):
        current = self.voice_in_use()
        for v in self.voices:
            self.voice_tree.set(v["description"], "use", "✓ in use" if v["description"] == current else "")
        if select and current and self.voice_tree.exists(current):
            self.voice_tree.selection_set(current)
            self.voice_tree.see(current)
        name = get(self.cfg, "voice.name")
        if name and current is None and self.voices and getattr(self, "_warned_missing", None) != name:
            self._warned_missing = name
            self.saved_label.configure(
                text=f"config.json asks for '{name}', which isn't installed here, so Tiger uses "
                     "the Windows default. Pick a voice and press Use this voice.")

    def selected_voice(self):
        sel = self.voice_tree.selection()
        return next((v for v in self.voices if sel and v["description"] == sel[0]), None)

    def update_slider_labels(self):
        step = int(round(self.rate_var.get()))
        self.rate_label.configure(text="Normal" if step == 0 else f"{step:+d}")
        self.vol_label.configure(text=f"{int(round(self.vol_var.get()))}%")

    def on_rate(self):
        from .audio import step_to_rate
        self.update_slider_labels()
        self.save_later("rate", lambda: {"voice.rate": step_to_rate(int(round(self.rate_var.get())))},
                        "Speed saved")

    def on_volume(self):
        self.update_slider_labels()
        self.save_later("volume", lambda: {"voice.volume": round(self.vol_var.get() / 100, 2)},
                        "Volume saved")

    def preview(self):
        from .audio import Speaker, step_to_rate
        v = self.selected_voice()
        if v is None:
            self.saved_label.configure(text="Pick a voice in the list first.")
            return
        if self._preview is None:
            self._preview = Speaker(True, voice_name=v["name"])
        self._preview.stop()
        self._preview.configure(voice_name=v["description"],
                                rate=step_to_rate(int(round(self.rate_var.get()))),
                                volume=self.vol_var.get() / 100)
        self._preview.say(self.preview_var.get().strip() or PREVIEW_TEXT)

    def stop_preview(self):
        if self._preview is not None:
            self._preview.stop()

    def use_voice(self):
        v = self.selected_voice()
        if v is None:
            self.saved_label.configure(text="Pick a voice in the list first.")
            return
        if self.save({"voice.name": v["name"]}, f"{v['name']} saved"):
            self.mark_voice_in_use()

    def use_default_voice(self):
        if self.save({"voice.name": None}, "Windows default voice saved"):
            self.mark_voice_in_use()

    # ------------------------------------------------------------------ microphone tab
    def build_mic_tab(self):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="Microphone")
        ttk.Label(tab, text="Pick the mic Tiger listens on, then talk from where you stand to hit. "
                            "The bar should jump well into the middle when you speak.",
                  style="Hint.TLabel", wraplength=590).pack(anchor="w")

        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="Microphone").pack(side="left", padx=(0, 10))
        self.mic_var = tk.StringVar()
        self.mic_combo = ttk.Combobox(row, textvariable=self.mic_var, state="readonly")
        self.mic_combo.pack(side="left", fill="x", expand=True)
        self.mic_combo.bind("<<ComboboxSelected>>", lambda e: self.start_meter())
        ttk.Button(row, text="Refresh", command=self.load_mics).pack(side="left", padx=(6, 0))

        meter = ttk.Frame(tab)
        meter.pack(fill="x", pady=(14, 0))
        ttk.Label(meter, text="Level").pack(side="left", padx=(0, 10))
        self.level_bar = ttk.Progressbar(meter, maximum=100)
        self.level_bar.pack(side="left", fill="x", expand=True)
        self.mic_msg = ttk.Label(tab, style="Hint.TLabel", wraplength=590)
        self.mic_msg.pack(anchor="w", pady=(6, 0))

        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Use this microphone", command=self.use_mic).pack(side="right")

        ttk.Separator(tab).pack(fill="x", pady=16)
        ttk.Label(tab, text="How sure Tiger must be before acting", style="Big.TLabel").pack(anchor="w")
        ttk.Label(tab, text="Move right if Tiger acts on things you didn't say. Move left if it "
                            "ignores you. 0.55 suits most rooms.",
                  style="Hint.TLabel", wraplength=590).pack(anchor="w", pady=(2, 6))
        conf = ttk.Frame(tab)
        conf.pack(fill="x")
        self.conf_var = tk.DoubleVar(value=float(self.cfg.get("min_confidence", 0.55)))
        ttk.Label(conf, text="Relaxed").pack(side="left")
        ttk.Scale(conf, from_=0.30, to=0.90, variable=self.conf_var,
                  command=lambda _: self.on_conf()).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(conf, text="Strict").pack(side="left")
        self.conf_label = ttk.Label(conf, width=6)
        self.conf_label.pack(side="left", padx=(10, 0))
        self.conf_label.configure(text=f"{self.conf_var.get():.2f}")
        self.load_mics()

    def load_mics(self):
        try:
            from .audio import input_devices
            self.mic_devices = input_devices()
            self.mic_error = None
        except Exception as e:
            self.mic_devices = []
            self.mic_error = f"Can't list microphones ({e})."
        names = ["Windows default microphone"] + [n for _, n in self.mic_devices]
        self.mic_combo["values"] = names
        want = get(self.cfg, "mic.device")
        current = "Windows default microphone"
        if want is not None:
            frag = str(want).lower()
            match = next((n for i, n in self.mic_devices
                          if (isinstance(want, int) and i == want) or frag in n.lower()), None)
            current = match or f"{want} (not plugged in?)"
        self.mic_var.set(current)
        self.mic_msg.configure(text=self.mic_error or "")

    def selected_mic(self):
        """(sounddevice index or None, name or None)"""
        name = self.mic_var.get()
        for i, n in self.mic_devices:
            if n == name:
                return i, n
        return None, None

    def start_meter(self):
        self.stop_meter()
        if self.nb.index(self.nb.select()) != 1:
            return
        try:
            import sounddevice as sd
            idx, _ = self.selected_mic()
            if idx is None and self.mic_var.get() != "Windows default microphone":
                self.mic_msg.configure(text="That microphone isn't connected right now.")
                return
            info = sd.query_devices(idx, "input")

            def callback(indata, frames, t, status):
                samples = array.array("h", bytes(indata))
                peak = max(map(abs, samples)) if samples else 0
                self.mic_level = max(self.mic_level * 0.6, peak / 32768.0)

            self.mic_stream = sd.RawInputStream(device=idx, channels=1, dtype="int16",
                                                samplerate=int(info["default_samplerate"]),
                                                blocksize=1024, callback=callback)
            self.mic_stream.start()
            self.mic_msg.configure(text=self.mic_error or "Listening. Say \"seven iron\" from the tee.")
        except Exception as e:
            self.mic_stream = None
            self.mic_msg.configure(text=f"Can't open that microphone ({e}).")

    def stop_meter(self):
        if self.mic_stream is not None:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            except Exception:
                pass
            self.mic_stream = None
        self.mic_level = 0.0
        self.level_bar["value"] = 0

    def update_meter(self):
        if self.mic_stream is None:
            return
        lvl = self.mic_level
        db = 20 * math.log10(lvl) if lvl > 0 else -60
        self.level_bar["value"] = max(0, min(100, (db + 60) / 60 * 100))
        self.mic_level *= 0.85

    def use_mic(self):
        idx, name = self.selected_mic()
        if name is None and self.mic_var.get() != "Windows default microphone":
            self.saved_label.configure(text="Pick a microphone that's plugged in.")
            return
        self.save({"mic.device": name}, f"{name or 'Windows default microphone'} saved")

    def on_conf(self):
        val = round(self.conf_var.get(), 2)
        self.conf_label.configure(text=f"{val:.2f}")
        self.save_later("conf", lambda: {"min_confidence": round(self.conf_var.get(), 2)},
                        "Sensitivity saved")

    # ------------------------------------------------------------------ distances tab
    def build_distance_tab(self):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="Distances")
        ttk.Label(tab, text="For the shot in front of you (\"what club should I hit\"), Tiger uses "
                            "Pureplay's suggested club, which comes from the player's own bag in "
                            "Pureplay, whenever club suggestion is on in Pureplay.\n\nThese "
                            "distances are only a backup: for \"what should I hit from one fifty\" "
                            "when that isn't the distance you have, and when club suggestion is off. "
                            "Carry in yards; leave a club blank if it isn't in your bag.",
                  style="Hint.TLabel", wraplength=590, justify="left").pack(anchor="w")
        grid = ttk.Frame(tab)
        grid.pack(fill="x", pady=(10, 0))
        carries = self.cfg.get("carry_yards") or {}
        clubs = CLUB_ORDER + [c for c in carries if c not in CLUB_ORDER]
        self.carry_vars = {}
        per_col = (len(clubs) + 1) // 2
        vcmd = (self.root.register(lambda s: s == "" or (s.isdigit() and len(s) <= 3)), "%P")
        for n, club in enumerate(clubs):
            col, row = divmod(n, per_col)
            ttk.Label(grid, text=club_label(club)).grid(row=row, column=col * 3, sticky="w",
                                                        padx=(0 if col == 0 else 30, 8), pady=2)
            var = tk.StringVar(value=str(carries[club]) if club in carries else "")
            ttk.Entry(grid, textvariable=var, width=6, validate="key",
                      validatecommand=vcmd).grid(row=row, column=col * 3 + 1, pady=2)
            ttk.Label(grid, text="yd", style="Hint.TLabel").grid(row=row, column=col * 3 + 2,
                                                                 sticky="w", padx=(4, 0))
            self.carry_vars[club] = var
        self.carry_msg = ttk.Label(tab, style="Bad.TLabel", wraplength=590)
        self.carry_msg.pack(anchor="w", pady=(10, 0))
        ttk.Button(tab, text="Save distances", command=self.save_distances).pack(anchor="e")

    def save_distances(self):
        carries = {c: int(v.get()) for c, v in self.carry_vars.items() if v.get().strip()}
        if not carries:
            self.carry_msg.configure(text="Enter at least one distance.")
            return
        ordered = [c for c in CLUB_ORDER if c in carries]
        odd = [(a, b) for a, b in zip(ordered, ordered[1:]) if carries[b] > carries[a]]
        self.carry_msg.configure(
            text="" if not odd else "Saved, but check: " + "; ".join(
                f"{club_label(b)} goes farther than {club_label(a).lower()}" for a, b in odd[:3]) + ".")
        self.save({"carry_yards": carries}, "Distances saved")

    # ------------------------------------------------------------------ status tab
    def build_status_tab(self):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="Status")
        info = ttk.Frame(tab)
        info.pack(fill="x")
        info.columnconfigure(1, weight=1)
        self.status_rows = {}
        for r, (key, label) in enumerate([("tiger", "Tiger"), ("pureplay", "Pureplay"),
                                          ("voice", "Voice"), ("mic", "Microphone"),
                                          ("message", "Last message")]):
            ttk.Label(info, text=label, style="Big.TLabel" if r < 2 else "TLabel").grid(
                row=r, column=0, sticky="nw", padx=(0, 16), pady=4)
            val = ttk.Label(info, wraplength=460, justify="left")
            val.grid(row=r, column=1, sticky="w", pady=4)
            self.status_rows[key] = val
        self.start_btn = ttk.Button(info, text="Start Tiger", command=self.start_tiger)
        self.start_btn.grid(row=0, column=2, sticky="e")

        ttk.Separator(tab).pack(fill="x", pady=16)
        ttk.Label(tab, text="Re-pair with Pureplay", style="Big.TLabel").pack(anchor="w")
        ttk.Label(tab, text="Use this if Pureplay shows a \"Read only\" tag next to Tiger, or Tiger "
                            "says it has no permission to change club or aim.\n"
                            "1. In Pureplay, open Settings > Accessories and click Remove next to "
                            "Tiger Voice Control.\n"
                            "2. Press the button below. Tiger forgets its old pairing and asks again.\n"
                            "3. In Pureplay, choose Aim and club (not Read only), then Allow.",
                  style="Hint.TLabel", wraplength=590, justify="left").pack(anchor="w", pady=(2, 8))
        ttk.Button(tab, text="Re-pair Tiger", command=self.repair).pack(anchor="w")

        ttk.Separator(tab).pack(fill="x", pady=16)
        files = ttk.Frame(tab)
        files.pack(fill="x")
        ttk.Button(files, text="Open Tiger folder",
                   command=lambda: self.open_path(self.base_dir)).pack(side="left")
        ttk.Button(files, text="Open config.json",
                   command=lambda: self.open_path(config_store.config_path(self.base_dir))).pack(
            side="left", padx=(6, 0))

    def refresh_status(self):
        running = tiger_is_running(self.base_dir)
        st = config_store.read_status(self.base_dir) or {}
        fresh = running and time.time() - st.get("updated", 0) < 8
        rows = self.status_rows
        if running:
            rows["tiger"].configure(text="Running", style="Good.TLabel")
            self.start_btn.state(["disabled"])
        else:
            rows["tiger"].configure(text="Not running", style="Bad.TLabel")
            self.start_btn.state(["!disabled"])
        if not fresh:
            rows["pureplay"].configure(text="Unknown (Tiger isn't running)" if not running
                                       else "Checking...", style="TLabel")
            for k in ("voice", "mic", "message"):
                rows[k].configure(text="")
            return
        if st.get("control"):
            rows["pureplay"].configure(text="Connected, with aim and club control", style="Good.TLabel")
        elif st.get("read_only"):
            rows["pureplay"].configure(text="Connected READ ONLY, so Tiger can't change club or aim. "
                                            "Re-pair below.", style="Bad.TLabel")
        elif st.get("pairing_pending"):
            rows["pureplay"].configure(text="Waiting for you to approve Tiger on the Pureplay screen "
                                            "(choose Aim and club)", style="Bad.TLabel")
        else:
            rows["pureplay"].configure(text="Not connected. Is Pureplay running, with the Accessory "
                                            "API on?", style="Bad.TLabel")
        rows["voice"].configure(text=st.get("voice") or "")
        rows["mic"].configure(text=st.get("mic") or "")
        msg = st.get("config_error") or st.get("message") or ""
        rows["message"].configure(text=msg.replace("\n", " ").replace("        ", " "))

    def start_tiger(self):
        bat = os.path.join(self.base_dir, "run_tiger.bat")
        if sys.platform != "win32" or not os.path.exists(bat):
            messagebox.showinfo("Tiger Settings", "Start Tiger with run_tiger.bat.")
            return
        self._launch_tiger()
        self.saved_label.configure(text="Starting Tiger...")

    def repair(self):
        if not messagebox.askyesno(
                "Re-pair Tiger",
                "Have you already clicked Remove next to Tiger Voice Control in Pureplay's "
                "Settings > Accessories?\n\nIf not, do that first, then press Yes."):
            return
        if tiger_is_running(self.base_dir):
            config_store.send_request(self.base_dir, "repair")
            self.saved_label.configure(text="Re-pairing. In Pureplay, choose Aim and club, then Allow.")
        else:
            try:
                os.remove(os.path.join(self.base_dir, "token.json"))
            except FileNotFoundError:
                pass
            except OSError as e:
                messagebox.showerror("Re-pair Tiger", f"Couldn't delete token.json: {e}")
                return
            self.saved_label.configure(text="Old pairing deleted. Start Tiger, then in Pureplay "
                                            "choose Aim and club, then Allow.")

    def open_path(self, path):
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    # ------------------------------------------------------------------ updates tab
    def build_update_tab(self):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="Updates")
        self.update_headline = ttk.Label(tab, text="Checking GitHub for updates...", style="Big.TLabel")
        self.update_headline.pack(anchor="w")
        info = ttk.Frame(tab)
        info.pack(fill="x", pady=(10, 0))
        info.columnconfigure(1, weight=1)
        ttk.Label(info, text="You have").grid(row=0, column=0, sticky="nw", padx=(0, 16), pady=3)
        self.update_mine = ttk.Label(info, wraplength=480, justify="left")
        self.update_mine.grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(info, text="Newest").grid(row=1, column=0, sticky="nw", padx=(0, 16), pady=3)
        self.update_latest = ttk.Label(info, wraplength=480, justify="left")
        self.update_latest.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(tab, text="Updating keeps your settings (voice, microphone, distances and everything "
                            "else in config.json), your Pureplay pairing and the speech model. If Tiger "
                            "is running, it's closed for the update and started again afterwards. "
                            "The files that get replaced are saved in the backups folder.",
                  style="Hint.TLabel", wraplength=590, justify="left").pack(anchor="w", pady=(12, 10))
        btns = ttk.Frame(tab)
        btns.pack(fill="x")
        self.update_btn = ttk.Button(btns, text="Update now", command=self.start_update)
        self.update_btn.pack(side="left")
        self.check_btn = ttk.Button(btns, text="Check again", command=self.check_updates)
        self.check_btn.pack(side="left", padx=(6, 0))
        self.reopen_btn = ttk.Button(btns, text="Restart Tiger Settings", command=self.reopen)
        self.update_log = ttk.Label(tab, wraplength=590, justify="left")
        self.update_log.pack(anchor="w", pady=(12, 0))
        self.show_installed()
        self.update_btn.state(["disabled"])
        self.root.after(800, self.check_updates)

    def show_installed(self):
        from .updater import installed_version
        mine = installed_version(self.base_dir)
        self.update_mine.configure(
            text=f"{mine['date']}  {mine['message']}" if mine else
            "Not recorded (Tiger was installed or updated by hand)")

    def run_in_background(self, work, done):
        """Run work() on a thread, then done(result or exception) on the UI thread."""
        def go():
            try:
                result = work()
            except Exception as e:
                result = e
            self._ui.put(lambda: done(result))
        threading.Thread(target=go, daemon=True).start()

    def check_updates(self):
        from .updater import latest_commit
        if self.updating:
            return
        self.check_btn.state(["disabled"])
        self.update_headline.configure(text="Checking GitHub for updates...", style="Big.TLabel")
        self.run_in_background(latest_commit, self.show_check)

    def show_check(self, latest):
        from .updater import is_current, installed_version
        self.check_btn.state(["!disabled"])
        if not isinstance(latest, dict):
            self.latest = None
            self.update_headline.configure(text="Couldn't reach GitHub. Check the internet connection.",
                                           style="Bad.TLabel")
            self.update_latest.configure(text="Unknown")
            self.update_btn.state(["disabled"])
            return
        self.latest = latest
        self.update_latest.configure(text=f"{latest['date']}  {latest['message']}")
        if is_current(self.base_dir, latest):
            self.update_headline.configure(text="You have the newest version.", style="Good.TLabel")
            self.update_btn.state(["disabled"])
            self.nb.tab(4, text="Updates")
        else:
            known = installed_version(self.base_dir) is not None
            self.update_headline.configure(
                text="An update is available." if known else
                "Update to make sure you have the newest version.", style="Bad.TLabel")
            self.update_btn.state(["!disabled"])
            self.nb.tab(4, text="Updates (new)")

    def start_update(self):
        if self.updating or not self.latest:
            return
        self.updating = True
        self.update_btn.state(["disabled"])
        self.check_btn.state(["disabled"])
        base, latest = self.base_dir, self.latest
        say = lambda text: self._ui.put(lambda: self.update_log.configure(text=text))

        def work():
            from .updater import download_and_install
            was_running = tiger_is_running(base)
            if was_running:
                say("Closing Tiger...")
                config_store.send_request(base, "quit")
                for _ in range(40):
                    time.sleep(0.5)
                    if not tiger_is_running(base):
                        break
                else:
                    raise RuntimeError("Tiger didn't close. Close its window yourself, then press "
                                       "Update now again.")
                time.sleep(0.5)
            say("Downloading and installing the update...")
            summary = download_and_install(base, latest)
            if was_running:
                say("Starting Tiger again...")
                self._launch_tiger()
            summary["was_running"] = was_running
            return summary

        self.run_in_background(work, self.update_finished)

    def update_finished(self, result):
        self.updating = False
        self.check_btn.state(["!disabled"])
        if isinstance(result, Exception):
            self.update_log.configure(text=f"The update didn't finish: {result}\nYour settings and pairing "
                                           "weren't touched.", style="Bad.TLabel")
            self.update_btn.state(["!disabled"])
            return
        n = len(result["changed"])
        lines = [f"Updated {n} file{'s' if n != 1 else ''}." if n else "Your files were already current."]
        if result["new_settings"]:
            lines.append("New settings added with their defaults: " + ", ".join(result["new_settings"]) + ".")
        if result.get("packages") and not result.get("packages_ok"):
            lines.append("Some Python packages couldn't be installed. Run setup.bat once.")
        if result["was_running"]:
            lines.append("Tiger has been started again.")
        lines.append("Restart Tiger Settings to use the new version of this window.")
        self.update_log.configure(text="\n".join(lines), style="Good.TLabel")
        self.show_installed()
        self.show_check(self.latest)
        self.reopen_btn.pack(side="left", padx=(6, 0))

    def reopen(self):
        script = os.path.join(self.base_dir, "tiger.py")
        flags = 0x00000008 if sys.platform == "win32" else 0      # DETACHED_PROCESS
        subprocess.Popen([sys.executable, script, "--settings"], cwd=self.base_dir, creationflags=flags)
        self.on_close()

    def _launch_tiger(self):
        bat = os.path.join(self.base_dir, "run_tiger.bat")
        if sys.platform == "win32" and os.path.exists(bat):
            subprocess.Popen(["cmd", "/c", "start", "Tiger", "/min", bat], cwd=self.base_dir,
                             creationflags=0x08000000)    # CREATE_NO_WINDOW

    # ------------------------------------------------------------------ housekeeping
    def on_tab_changed(self, _):
        if self.nb.index(self.nb.select()) == 1:
            self.start_meter()
        else:
            self.stop_meter()
        if self.nb.index(self.nb.select()) == 3:
            self.refresh_status()

    def tick(self):
        """Keep up with changes made elsewhere (e.g. "Tiger, switch to Linda")."""
        try:
            while True:
                try:
                    self._ui.get_nowait()()
                except queue.Empty:
                    break
            self.update_meter()
            now = time.monotonic()
            if now - getattr(self, "_last_slow", 0) > 1.5:
                self._last_slow = now
                mtime = config_store.config_mtime(self.base_dir)
                if mtime != self._cfg_mtime:
                    self.load_config()
                    self.show_config_error()
                    if not self.cfg_error and not self._save_jobs:
                        from .audio import rate_to_step
                        v = self.cfg.get("voice", {})
                        self.rate_var.set(rate_to_step(v.get("rate", 190)))
                        self.vol_var.set(int(round(float(v.get("volume", 1.0)) * 100)))
                        self.update_slider_labels()
                self.mark_voice_in_use()
                if self.nb.index(self.nb.select()) == 3:
                    self.refresh_status()
        finally:
            self.root.after(80, self.tick)

    def on_close(self):
        if self.updating and not messagebox.askyesno(
                "Tiger Settings", "An update is still running. Close anyway?"):
            return
        for job, run in list(self._save_jobs.values()):   # finish saves still waiting
            self.root.after_cancel(job)
            run()
        self.stop_meter()
        self.stop_preview()
        self.root.destroy()


def main(base_dir):
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)    # crisp text on high-DPI screens
    except Exception:
        pass
    try:
        root = tk.Tk()
    except tk.TclError as e:
        print(f"Can't open a window: {e}")
        return

    def report(exc, val, tb):
        import traceback
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(os.path.join(base_dir, "settings_log.txt"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
        except OSError:
            pass
        messagebox.showerror("Tiger Settings", f"Something went wrong:\n{val}\n\n"
                                               "Details are in settings_log.txt.")
    root.report_callback_exception = report
    try:
        SettingsWindow(root, base_dir)
    except Exception:
        report(*sys.exc_info())
        root.destroy()
        return
    root.mainloop()
