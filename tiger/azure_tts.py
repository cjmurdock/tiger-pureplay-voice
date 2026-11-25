"""Microsoft Azure neural voices, over Azure's REST API (no extra packages needed).

You need an Azure Speech resource (the Free F0 tier covers 500,000 characters a month of the
regular neural voices) and its key and region, entered in Tiger Settings.
"""
import json
import os
import time
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

# 24 kHz, 16-bit mono WAV: plays everywhere with no decoder, and is easy to cut into sentences.
OUTPUT_FORMAT = "riff-24khz-16bit-mono-pcm"
SAMPLE_RATE = 24000


class AzureError(Exception):
    def __init__(self, message, status=None, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def rate_percent(step):
    """Tiger's speed step (-5..+10, 0 = normal) as an SSML prosody rate."""
    return f"{int(step) * 10:+d}%"


class AzureTTS:
    def __init__(self, key, region, timeout=10, endpoint=None):
        self.key = (key or "").strip()
        self.region = (region or "").strip().lower().replace(" ", "")
        self.timeout = timeout
        self.endpoint = endpoint or os.environ.get("TIGER_AZURE_ENDPOINT")   # tests only

    @property
    def configured(self):
        return bool(self.key and self.region)

    def _url(self, path):
        base = self.endpoint or f"https://{self.region}.tts.speech.microsoft.com"
        return f"{base}/cognitiveservices/{path}"

    def _request(self, path, data=None, headers=None, timeout=None):
        if not self.configured:
            raise AzureError("No Azure key and region in Tiger Settings.")
        h = {"Ocp-Apim-Subscription-Key": self.key, "User-Agent": "Tiger-voice-control"}
        h.update(headers or {})
        req = urllib.request.Request(self._url(path), data=data, headers=h,
                                     method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            retry = e.headers.get("Retry-After") if e.headers else None
            msg = {401: "Azure didn't accept the key. Check the key and region in Tiger Settings.",
                   403: "Azure refused the request. Check the key and region in Tiger Settings.",
                   429: "Azure asked Tiger to slow down."}.get(e.code, f"Azure answered {e.code}.")
            raise AzureError(msg, e.code, float(retry) if retry and retry.isdigit() else None) from None
        except (urllib.error.URLError, OSError) as e:
            raise AzureError(f"Couldn't reach Azure ({getattr(e, 'reason', e)}).") from None

    def list_voices(self):
        """English voices: [{'id', 'name', 'accent', 'gender', 'type', 'locale'}], by accent then name."""
        data = json.loads(self._request("voices/list"))
        out = []
        for v in data:
            if not str(v.get("Locale", "")).startswith("en-"):
                continue
            out.append({"id": v["ShortName"], "name": v.get("DisplayName") or v["ShortName"],
                        "accent": v.get("LocaleName") or v.get("Locale"),
                        "gender": v.get("Gender", ""), "type": v.get("VoiceType", ""),
                        "locale": v.get("Locale")})
        out.sort(key=lambda v: (v["accent"], v["name"]))
        return out

    def ssml(self, sentences, voice, rate_step=0, gap_ms=0):
        lang = "-".join(voice.split("-")[:2]) or "en-US"
        joined = f'<break time="{gap_ms}ms"/>'.join(escape(s) for s in sentences)
        return (f"<speak version='1.0' xml:lang='{lang}'><voice name='{escape(voice)}'>"
                f"<prosody rate='{rate_percent(rate_step)}'>{joined}</prosody></voice></speak>")

    def synthesize(self, sentences, voice, rate_step=0, gap_ms=0, timeout=None):
        """WAV bytes for one sentence, or several separated by gap_ms of silence."""
        if isinstance(sentences, str):
            sentences = [sentences]
        body = self.ssml(sentences, voice, rate_step, gap_ms).encode("utf-8")
        return self._request("v1", data=body, timeout=timeout,
                             headers={"Content-Type": "application/ssml+xml",
                                      "X-Microsoft-OutputFormat": OUTPUT_FORMAT})


def synthesize_with_retry(tts, sentences, voice, rate_step=0, gap_ms=0, tries=5, on_wait=None,
                          timeout=90):
    """Like synthesize(), but waits and retries when Azure says to slow down."""
    for attempt in range(tries):
        try:
            return tts.synthesize(sentences, voice, rate_step, gap_ms, timeout=timeout)
        except AzureError as e:
            if e.status != 429 or attempt == tries - 1:
                raise
            wait = e.retry_after or min(60, 5 * (attempt + 1))
            if on_wait:
                on_wait(wait)
            time.sleep(wait)
