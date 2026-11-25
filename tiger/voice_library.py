"""A library of Azure voice clips on this PC, one WAV per sentence Tiger can say.

    voices\\azure\\<voice id>\\speed<step>\\<key>.wav

Downloading asks Azure for many sentences at once with a long pause between them, then cuts the
audio at those pauses, so a whole library takes a few hundred requests rather than thousands.
A reply is played by joining its sentences' clips (with a short natural gap) into one sound.

Playback uses Windows' built-in winsound, so nothing extra needs installing.
"""
import array
import hashlib
import io
import os
import sys
import threading
import time
import wave

from .azure_tts import SAMPLE_RATE, AzureError, synthesize_with_retry
from .lines import normalize, split_sentences

GAP_MS = 1500              # silence Azure is asked to put between sentences in a batch
SPLIT_MIN_MS = 900         # a silence this long is a cut between sentences
SILENCE = 350              # sample level counted as silence (16-bit)
PAD_MS = 60                # silence kept at each end of a clip
JOIN_GAP_MS = 140          # pause between sentences when a reply is played
BATCH = 40                 # sentences per Azure request when downloading


def library_root(base_dir):
    return os.path.join(base_dir, "voices", "azure")


def _safe(name):
    return "".join(ch for ch in name if ch.isalnum() or ch in "-_+") or "voice"


# ---------- WAV helpers ----------
def pcm_from_wav(data):
    """16-bit mono samples from Azure's RIFF WAV (found by its data chunk, whatever the sizes say)."""
    i = data.find(b"data")
    if i < 0:
        raise AzureError("Azure sent audio Tiger can't read.")
    pcm = data[i + 8:]
    pcm = pcm[:len(pcm) - (len(pcm) % 2)]
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def wav_bytes(samples, rate=SAMPLE_RATE):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        s = samples
        if sys.byteorder == "big":
            s = array.array("h", samples)
            s.byteswap()
        w.writeframes(s.tobytes())
    return buf.getvalue()


def read_wav(path):
    with wave.open(path, "rb") as w:
        samples = array.array("h")
        samples.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def _frames_silent(samples, frame):
    out = []
    for i in range(0, len(samples), frame):
        chunk = samples[i:i + frame]
        out.append(max(map(abs, chunk)) < SILENCE if len(chunk) else True)
    return out


def trim(samples, rate=SAMPLE_RATE):
    frame = rate // 100
    silent = _frames_silent(samples, frame)
    if all(silent):
        return samples
    first = silent.index(False)
    last = len(silent) - 1 - silent[::-1].index(False)
    pad = PAD_MS * rate // 1000
    start = max(0, first * frame - pad)
    end = min(len(samples), (last + 1) * frame + pad)
    return samples[start:end]


def split_on_gaps(samples, count, rate=SAMPLE_RATE):
    """Cut audio of `count` sentences at the long silences between them; None if it doesn't fit."""
    if count == 1:
        return [trim(samples, rate)]
    frame = rate // 100
    silent = _frames_silent(samples, frame)
    runs, start = [], None
    for i, s in enumerate(silent + [False]):
        if s and start is None:
            start = i
        elif not s and start is not None:
            runs.append((start, i))
            start = None
    min_frames = SPLIT_MIN_MS // 10
    # ignore silence before the first word and after the last
    first_sound = silent.index(False) if False in silent else 0
    last_sound = len(silent) - 1 - silent[::-1].index(False) if False in silent else 0
    gaps = [r for r in runs if r[1] - r[0] >= min_frames and r[0] > first_sound and r[1] <= last_sound]
    if len(gaps) < count - 1:
        return None
    gaps = sorted(sorted(gaps, key=lambda r: r[1] - r[0], reverse=True)[:count - 1])
    cuts = [0] + [((a + b) // 2) * frame for a, b in gaps] + [len(samples)]
    return [trim(samples[cuts[i]:cuts[i + 1]], rate) for i in range(count)]


def join_clips(clips, volume=1.0, rate=SAMPLE_RATE):
    gap = array.array("h", bytes(2 * (JOIN_GAP_MS * rate // 1000)))
    out = array.array("h")
    for i, c in enumerate(clips):
        if i:
            out.extend(gap)
        out.extend(c)
    if volume < 0.999:
        v = max(0.0, float(volume))
        out = array.array("h", (int(x * v) for x in out))
    return out


# ---------- playback ----------
class Player:
    """Plays a sound and can be cut off. Windows only; elsewhere it just waits (for testing)."""

    def __init__(self, folder):
        self.folder = folder
        self._n = 0

    def play(self, samples, interrupt, rate=SAMPLE_RATE):
        os.makedirs(self.folder, exist_ok=True)
        self._n = (self._n + 1) % 2
        path = os.path.join(self.folder, f"_playing{self._n}.wav")
        with open(path, "wb") as f:
            f.write(wav_bytes(samples, rate))
        seconds = len(samples) / rate
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        end = time.monotonic() + seconds + 0.05
        while time.monotonic() < end:
            if interrupt.wait(0.05):
                if sys.platform == "win32":
                    import winsound
                    winsound.PlaySound(None, winsound.SND_PURGE)
                return False
        return True


# ---------- the library ----------
class VoiceLibrary:
    def __init__(self, base_dir, voice_id, rate_step=0):
        self.base_dir = base_dir
        self.voice_id = voice_id
        self.rate_step = int(rate_step)
        self.folder = os.path.join(library_root(base_dir), _safe(voice_id),
                                   f"speed{self.rate_step:+d}")
        self._lock = threading.Lock()

    def path(self, sentence):
        key = hashlib.sha1(normalize(sentence).encode("utf-8")).hexdigest()[:20]
        return os.path.join(self.folder, key + ".wav")

    def has(self, sentence):
        return os.path.exists(self.path(sentence))

    def count(self, sentences):
        return sum(1 for s in sentences if self.has(s))

    def save(self, sentence, samples):
        os.makedirs(self.folder, exist_ok=True)
        dest = self.path(sentence)
        tmp = f"{dest}.{threading.get_ident()}.tmp"
        with open(tmp, "wb") as f:
            f.write(wav_bytes(samples))
        os.replace(tmp, dest)

    def fetch(self, tts, sentence, timeout=None):
        """Get one sentence from Azure and keep it. Raises AzureError."""
        data = tts.synthesize([sentence], self.voice_id, self.rate_step, timeout=timeout)
        samples = trim(pcm_from_wav(data))
        self.save(sentence, samples)
        return samples

    def clips_for(self, text, tts=None, timeout=3):
        """Clips for each sentence of text. Returns (clips, leftover_text): leftover is the part
        that couldn't be got (offline, no key...) and should be spoken another way."""
        sentences = split_sentences(text)
        clips = []
        for i, s in enumerate(sentences):
            p = self.path(s)
            try:
                if os.path.exists(p):
                    clips.append(read_wav(p))
                    continue
            except (OSError, wave.Error, EOFError):
                pass
            if tts is None or not tts.configured:
                return clips, " ".join(sentences[i:])
            try:
                clips.append(self.fetch(tts, s, timeout=timeout))
            except AzureError:
                return clips, " ".join(sentences[i:])
        return clips, ""

    def download(self, tts, sentences, progress=None, stop=None, batch=BATCH):
        """Fill the library with every sentence that's missing. progress(done, total, note)."""
        todo = [s for s in sentences if not self.has(s)]
        total, done = len(sentences), len(sentences) - len(todo)
        say = progress or (lambda *a: None)
        say(done, total, "")
        i = 0
        while i < len(todo):
            if stop is not None and stop.is_set():
                say(done, total, "Stopped.")
                return done, total
            group = todo[i:i + batch]
            wait_note = lambda secs: say(done, total, f"Azure asked to slow down; waiting {int(secs)} s...")
            data = synthesize_with_retry(tts, group, self.voice_id, self.rate_step, GAP_MS,
                                         on_wait=wait_note)
            pieces = split_on_gaps(pcm_from_wav(data), len(group))
            if pieces is None:
                # Couldn't find every pause: get this batch one sentence at a time instead.
                pieces = []
                for s in group:
                    if stop is not None and stop.is_set():
                        break
                    pieces.append(trim(pcm_from_wav(synthesize_with_retry(
                        tts, [s], self.voice_id, self.rate_step, on_wait=wait_note))))
            for s, clip in zip(group, pieces):
                self.save(s, clip)
                done += 1
            i += len(group)
            say(done, total, "")
        say(done, total, "Done.")
        return done, total


# ---------- Azure voice list, cached so Tiger can offer voices without asking Azure ----------
def voice_list_path(base_dir):
    return os.path.join(library_root(base_dir), "voices.json")


def save_voice_list(base_dir, voices):
    import json
    os.makedirs(library_root(base_dir), exist_ok=True)
    tmp = voice_list_path(base_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(voices, f, indent=1)
    os.replace(tmp, voice_list_path(base_dir))


def load_voice_list(base_dir):
    import json
    try:
        with open(voice_list_path(base_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def downloaded_voices(base_dir):
    """Azure voice ids that have a library folder on this PC."""
    root = library_root(base_dir)
    try:
        return sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    except OSError:
        return []
