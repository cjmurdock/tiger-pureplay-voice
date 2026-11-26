"""Check that the speech model knows a word (used before changing the wake word).

Vosk only reports unknown words in its log, so the check runs in a separate quiet Python process
and reads that log. Returns True (known), False (unknown) or None (couldn't check).
"""
import os
import subprocess
import sys

_CODE = r"""
import json, sys
from vosk import Model, KaldiRecognizer, SetLogLevel
SetLogLevel(-1)
m = Model(sys.argv[1])
SetLogLevel(0)
KaldiRecognizer(m, 16000, json.dumps([sys.argv[2], "[unk]"]))
"""


def model_dir(base_dir, cfg):
    path = cfg.get("vosk_model", "models/vosk-model-small-en-us-0.15")
    return path if os.path.isabs(path) else os.path.join(base_dir, path)


def word_known(base_dir, cfg, word, timeout=90):
    model = model_dir(base_dir, cfg)
    if not os.path.isdir(model):
        return None
    python = sys.executable
    if python.lower().endswith("pythonw.exe"):
        python = python[:-len("pythonw.exe")] + "python.exe"
    try:
        r = subprocess.run([python, "-c", _CODE, model, word.lower()], capture_output=True,
                           timeout=timeout, creationflags=0x08000000 if sys.platform == "win32" else 0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    log = (r.stderr or b"").decode("utf-8", "replace") + (r.stdout or b"").decode("utf-8", "replace")
    if r.returncode != 0:
        return None
    return "missing in vocabulary" not in log
