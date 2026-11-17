"""Optional: dim or brighten the sim room lights through the Home Assistant REST API."""
import json
import logging
import urllib.request

log = logging.getLogger("tiger.ha")


def set_light(cfg, level):
    """level: "dim" or "bright". Blocking; call from a worker thread."""
    pct = cfg["dim_brightness_pct"] if level == "dim" else cfg["bright_brightness_pct"]
    url = cfg["url"].rstrip("/") + "/api/services/light/turn_on"
    body = json.dumps({"entity_id": cfg["light_entity"], "brightness_pct": pct}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return 200 <= r.status < 300
