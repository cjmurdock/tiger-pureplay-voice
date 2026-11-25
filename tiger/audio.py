"""Microphone capture + Vosk recognition (listener) and text-to-speech (speaker)."""
import json
import logging
import os
import queue
import sys
import threading

log = logging.getLogger("tiger.audio")


# config "voice.rate" is roughly words per minute (180 is normal). SAPI wants a step from
# -10 (slowest) to 10 (fastest), one step per 20 wpm.
RATE_NORMAL = 180
RATE_MIN_STEP, RATE_MAX_STEP = -5, 10


def rate_to_step(rate):
    try:
        return max(-10, min(10, round((float(rate) - RATE_NORMAL) / 20)))
    except (TypeError, ValueError):
        return 0


def step_to_rate(step):
    return RATE_NORMAL + 20 * int(step)


class Speaker:
    """Speaks replies on its own thread. While it talks, the listener ignores the mic.

    configure() changes the voice, speed and volume while Tiger is running; the change is
    applied on the speech thread (SAPI objects belong to the thread that made them) and
    takes effect from the next thing Tiger says.
    """

    def __init__(self, enabled=True, rate=190, volume=1.0, voice_name=None, on_message=None,
                 engine="windows", azure=None, base_dir=None):
        self.enabled = enabled
        self.rate = rate
        self.volume = volume
        self.voice_name = voice_name
        self.engine = engine or "windows"  # "windows" (SAPI) or "azure"
        self.azure = dict(azure or {})     # {"key", "region", "voice"}
        self.base_dir = base_dir
        self._azure_lib = None
        self._azure_warned = False
        self.on_message = on_message      # fn(text) for warnings the user should see
        self.active_voice = None          # description of the voice actually in use
        self.speaking = threading.Event()
        self._interrupt = threading.Event()
        self._q = queue.Queue()
        threading.Thread(target=self._run, name="speaker", daemon=True).start()

    def say(self, text):
        print(f"  Tiger: {text}")
        if self.enabled:
            self._q.put(("say", text))

    def wait_until_done(self):
        self._q.join()

    def beep(self):
        self._q.put(("beep", None))

    def configure(self, voice_name=None, rate=None, volume=None, enabled=None, engine=None,
                  azure=None):
        """Change settings live. Leave an argument as None to keep it."""
        self._q.put(("config", {"voice_name": voice_name, "rate": rate, "volume": volume,
                                "enabled": enabled, "engine": engine, "azure": azure}))

    def stop(self):
        """Cut off anything being said or waiting to be said (used by Settings previews)."""
        keep = []
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item[0] == "config":       # never drop a settings change
                keep.append(item)
            self._q.task_done()
        self._interrupt.set()
        for item in keep:
            self._q.put(item)

    def _message(self, text):
        log.warning(text)
        if self.on_message:
            self.on_message(text)

    def _make_engine(self):
        """Windows' built-in SAPI voice, driven directly (synchronous Speak on this thread)."""
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        self._default_token = voice.Voice
        self._apply(voice)
        return voice

    def _apply(self, voice):
        token = find_voice_token(self.voice_name) if self.voice_name else None
        if token is not None:
            voice.Voice = token
        else:
            voice.Voice = self._default_token
            if self.voice_name:
                self._message(f"The voice '{self.voice_name}' isn't installed on this PC, so I'm using "
                              f"the Windows default ({self._default_token.GetDescription()}). "
                              "Pick another in Tiger Settings, or run 'python tiger.py --list-voices'.")
        self.active_voice = voice.Voice.GetDescription()
        if self.engine == "azure" and self.azure.get("voice"):
            self.active_voice = f"Azure: {self.azure['voice']} (fallback: {self.active_voice})"
        log.info("Voice: %s", self.active_voice)
        voice.Rate = rate_to_step(self.rate)
        voice.Volume = max(0, min(100, int(round(float(self.volume) * 100))))

    def library(self):
        """The Azure voice library for the current voice and speed (created on demand)."""
        from .voice_library import VoiceLibrary
        voice, step = self.azure.get("voice"), max(RATE_MIN_STEP, min(RATE_MAX_STEP, rate_to_step(self.rate)))
        lib = self._azure_lib
        if lib is None or lib.voice_id != voice or lib.rate_step != step:
            lib = self._azure_lib = VoiceLibrary(self.base_dir or ".", voice, step)
        return lib

    def _say_azure(self, text):
        """Play text from the Azure voice library, fetching any missing sentence. Returns the
        part that couldn't be played (to be spoken by the Windows voice instead)."""
        from .azure_tts import AzureTTS
        from .voice_library import Player, join_clips
        lib = self.library()
        tts = AzureTTS(self.azure.get("key"), self.azure.get("region"))
        clips, leftover = lib.clips_for(text, tts, timeout=3)
        if clips:
            player = Player(os.path.dirname(lib.folder))
            if not player.play(join_clips(clips, self.volume), self._interrupt):
                return ""                                 # cut off on purpose
        if leftover and not self._azure_warned:
            self._azure_warned = True
            self._message("Azure isn't answering (or has no key), so I'm using the Windows voice for "
                          "lines that aren't in the voice library yet.")
        elif not leftover:
            self._azure_warned = False
        return leftover

    def _run(self):
        engine = None
        try:
            engine = self._make_engine()
        except Exception as e:   # not Windows, or pywin32 missing
            if self.enabled:
                log.warning("Voice output unavailable (%s); replies will be printed only.", e)
        while True:
            kind, data = self._q.get()
            self.speaking.set()
            try:
                if kind == "beep":
                    if sys.platform == "win32":
                        import winsound
                        winsound.Beep(1200, 90)
                elif kind == "config":
                    if data["enabled"] is not None:
                        self.enabled = data["enabled"]
                    if data["voice_name"] is not None:
                        self.voice_name = data["voice_name"] or None
                    if data["rate"] is not None:
                        self.rate = data["rate"]
                    if data["volume"] is not None:
                        self.volume = data["volume"]
                    if data.get("engine") is not None:
                        self.engine = data["engine"] or "windows"
                    if data.get("azure") is not None:
                        self.azure = dict(data["azure"])
                        self._azure_warned = False
                    if engine is not None:
                        self._apply(engine)
                    elif self.engine == "azure" and self.azure.get("voice"):
                        self.active_voice = f"Azure: {self.azure['voice']}"
                else:
                    self._interrupt.clear()
                    if self.engine == "azure" and self.azure.get("voice"):
                        data = self._say_azure(data)       # what's left if Azure couldn't say it
                    if not data or engine is None:
                        continue
                    engine.Speak(data, 1)                  # SVSFlagsAsync
                    while not engine.WaitUntilDone(100):
                        if self._interrupt.is_set():
                            engine.Speak("", 3)            # async + purge: stop talking
                            break
            except Exception:
                log.exception("Speech failed")
            finally:
                if self._q.empty():
                    self.speaking.clear()
                self._q.task_done()


# Classic SAPI voices, plus the newer "OneCore" voices Windows installs for Narrator and
# language packs (often more of them, e.g. Mark, George, Hazel); SAPI can use both.
VOICE_CATEGORIES = [
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices",
]

_VENDOR_WORDS = {"microsoft"}
_EXTRA_WORDS = {"desktop", "mobile", "online", "natural", "voice"}


def short_voice_name(desc):
    """'Microsoft David Desktop - English (United States)' -> 'David'."""
    head = desc.split(" - ")[0]
    words = [w for w in head.split() if w.lower() not in _VENDOR_WORDS | _EXTRA_WORDS]
    return " ".join(words) or head


def voice_language(desc):
    """'Microsoft Linda - English (Canada)' -> 'English (Canada)'."""
    return desc.split(" - ", 1)[1].strip() if " - " in desc else ""


def _voice_tokens():
    import win32com.client
    seen = set()
    for cat_id in VOICE_CATEGORIES:
        try:
            cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
            cat.SetId(cat_id, False)
            tokens = cat.EnumerateTokens()
        except Exception:
            continue
        for i in range(tokens.Count):
            t = tokens.Item(i)
            desc = t.GetDescription()
            # The same person often appears twice (classic + OneCore); keep the first.
            key = (short_voice_name(desc).lower(), voice_language(desc).lower())
            if desc not in seen and key not in seen:
                seen.add(desc)
                seen.add(key)
                yield t, desc


def _attr(token, name):
    try:
        return token.GetAttribute(name) or ""
    except Exception:
        return ""


def voice_info():
    """[{'name': 'Linda', 'description': ..., 'language': 'English (Canada)', 'gender': 'Female'}]"""
    import pythoncom
    pythoncom.CoInitialize()
    out = []
    for t, desc in _voice_tokens():
        out.append({"name": short_voice_name(desc), "description": desc,
                    "language": voice_language(desc), "gender": _attr(t, "Gender")})
    return out


def list_voices():
    return [v["description"] for v in voice_info()]


def find_voice_token(name_part):
    """Exact short name first ('Mark'), then any voice whose description contains the text."""
    want = name_part.lower().strip()
    tokens = list(_voice_tokens())
    for t, desc in tokens:
        if short_voice_name(desc).lower() == want or desc.lower() == want:
            return t
    for t, desc in tokens:
        if want in desc.lower():
            return t
    return None


def list_mics():
    import sounddevice as sd
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append(f"{i:3d}  {d['name']}  ({sd.query_hostapis(d['hostapi'])['name']})")
    return out


def input_devices():
    """Microphones as [(index, name)]. Windows lists each mic once per audio system (MME,
    DirectSound, WASAPI...); only the first system's entries are shown, because that's the
    one Tiger opens (see _resolve_device)."""
    import sounddevice as sd
    out, seen = [], set()
    devices = list(enumerate(sd.query_devices()))
    first_api = next((d["hostapi"] for _, d in devices if d["max_input_channels"] > 0), None)
    for i, d in devices:
        name = d["name"].strip()
        if "sound mapper" in name.lower() or "primary sound capture" in name.lower():
            continue    # Windows' stand-ins for "the default mic", offered separately
        if d["max_input_channels"] > 0 and d["hostapi"] == first_api and name.lower() not in seen:
            seen.add(name.lower())
            out.append((i, name))
    return out


def _resolve_device(device):
    """Accept an index, a name fragment like "TONOR", or None for the Windows default."""
    if device is None or isinstance(device, int):
        return device
    import sounddevice as sd
    frag = str(device).lower()
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and frag in d["name"].lower():
            return i
    log.warning("No microphone matching '%s'; using the default.", device)
    return None


class Listener:
    """Streams the mic into a grammar-limited Vosk recogniser and calls on_text(text, conf)."""

    def __init__(self, model_path, grammar, on_text, device=None, sample_rate=16000, speaker=None):
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        self.model = Model(model_path)
        self.grammar_json = json.dumps(grammar)
        self.sample_rate = sample_rate
        self.device = _resolve_device(device)
        self.on_text = on_text
        self.speaker = speaker
        self._KaldiRecognizer = KaldiRecognizer
        self._reopen = threading.Event()

    def _new_recognizer(self):
        rec = self._KaldiRecognizer(self.model, self.sample_rate, self.grammar_json)
        rec.SetWords(True)
        return rec

    def set_device(self, device):
        """Switch microphones while running (from config.json / Tiger Settings)."""
        self.device = _resolve_device(device)
        self._reopen.set()

    def describe_device(self):
        if self.device is None:
            return "Windows default microphone"
        try:
            import sounddevice as sd
            return sd.query_devices(self.device)["name"]
        except Exception:
            return f"device {self.device}"

    def run(self, stop_event):
        import sounddevice as sd
        while not stop_event.is_set():
            self._reopen.clear()
            try:
                self._listen(sd, stop_event)
            except Exception as e:
                # e.g. the mic was unplugged or the chosen one can't be opened
                log.warning("Microphone problem (%s). Trying again in 3 seconds.", e)
                if self._reopen.wait(3):
                    continue

    def _listen(self, sd, stop_event):
        audio_q = queue.Queue()

        def callback(indata, frames, t, status):
            audio_q.put(bytes(indata))

        rec = self._new_recognizer()
        muted = False
        with sd.RawInputStream(samplerate=self.sample_rate, blocksize=4000, device=self.device,
                               dtype="int16", channels=1, callback=callback):
            log.info("Listening on %s", self.describe_device())
            while not stop_event.is_set() and not self._reopen.is_set():
                try:
                    data = audio_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if self.speaker is not None and self.speaker.speaking.is_set():
                    muted = True          # don't let Tiger hear itself
                    continue
                if muted:
                    rec = self._new_recognizer()
                    muted = False
                if rec.AcceptWaveform(data):
                    self._emit(json.loads(rec.Result()))

    def _emit(self, result):
        text = result.get("text", "").strip()
        if not text or text == "[unk]":
            return
        words = result.get("result") or []
        conf = sum(w.get("conf", 0) for w in words) / len(words) if words else 0.0
        self.on_text(text, conf)
