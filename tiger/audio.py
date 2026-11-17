"""Microphone capture + Vosk recognition (listener) and text-to-speech (speaker)."""
import json
import logging
import queue
import sys
import threading

log = logging.getLogger("tiger.audio")


class Speaker:
    """Speaks replies on its own thread. While it talks, the listener ignores the mic."""

    def __init__(self, enabled=True, rate=190, volume=1.0, voice_name=None):
        self.enabled = enabled
        self.rate = rate
        self.volume = volume
        self.voice_name = voice_name
        self.speaking = threading.Event()
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

    def _make_engine(self):
        """Windows' built-in SAPI voice, driven directly (synchronous Speak on this thread)."""
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        if self.voice_name:
            token = find_voice_token(self.voice_name)
            if token is not None:
                voice.Voice = token
                log.info("Voice: %s", token.GetDescription())
            else:
                log.warning("No voice matching '%s'; using the Windows default. "
                            "Run 'python tiger.py --list-voices' to see the names.", self.voice_name)
        # config "rate" is words per minute (~180 is normal); SAPI wants -10..10
        voice.Rate = max(-10, min(10, round((self.rate - 180) / 20)))
        voice.Volume = max(0, min(100, int(self.volume * 100)))
        return voice

    def _run(self):
        engine = None
        if self.enabled:
            try:
                engine = self._make_engine()
            except Exception as e:   # not Windows, or pywin32 missing
                log.warning("Voice output unavailable (%s); replies will be printed only.", e)
        while True:
            kind, text = self._q.get()
            self.speaking.set()
            try:
                if kind == "beep":
                    if sys.platform == "win32":
                        import winsound
                        winsound.Beep(1200, 90)
                elif engine is not None:
                    engine.Speak(text)
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
            if desc not in seen:
                seen.add(desc)
                yield t, desc


def list_voices():
    import pythoncom
    pythoncom.CoInitialize()
    return [desc for _, desc in _voice_tokens()]


def find_voice_token(name_part):
    name_part = name_part.lower()
    for t, desc in _voice_tokens():
        if name_part in desc.lower():
            return t
    return None


def list_mics():
    import sounddevice as sd
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append(f"{i:3d}  {d['name']}  ({sd.query_hostapis(d['hostapi'])['name']})")
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

    def _new_recognizer(self):
        rec = self._KaldiRecognizer(self.model, self.sample_rate, self.grammar_json)
        rec.SetWords(True)
        return rec

    def run(self, stop_event):
        import sounddevice as sd
        audio_q = queue.Queue()

        def callback(indata, frames, t, status):
            audio_q.put(bytes(indata))

        rec = self._new_recognizer()
        muted = False
        with sd.RawInputStream(samplerate=self.sample_rate, blocksize=4000, device=self.device,
                               dtype="int16", channels=1, callback=callback):
            log.info("Listening on %s", "default microphone" if self.device is None else f"device {self.device}")
            while not stop_event.is_set():
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
