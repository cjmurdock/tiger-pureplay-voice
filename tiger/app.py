"""Tiger: voice control for Pureplay golf."""
import argparse
import asyncio
import json
import logging
import os
import sys
import threading

from . import keys
from .commands import Vocabulary, club_spoken, pick_club_for, number_phrases
from .pureplay_api import PurePlayClient, ApiError

log = logging.getLogger("tiger")

M_TO_YD = 1.09361
M_TO_FT = 3.28084

BLOCKER_WORDS = {
    "shot_in_progress": "the ball's still moving",
    "not_in_play": "there's no round in play",
    "interrupted": "the game is between phases",
    "not_your_turn": "nobody is up",
    "awaiting_decision": "the game is waiting on a ruling",
    "controls_disabled": "turn on Let Apps Change Aim and Club in Pureplay's Accessories settings",
}


def spoken_number(n):
    n = int(round(n))
    return number_phrases(n)[0] if 0 < n < 400 else str(n)


class Tiger:
    def __init__(self, cfg, base_dir, speaker, dry_run=False):
        self.cfg = cfg
        self.base_dir = base_dir
        self.speaker = speaker
        self.dry_run = dry_run
        self.vocab = Vocabulary.build(cfg.get("wake_word", "tiger"))
        self.sleeping = False
        self.announced_shots = set()
        self.api = PurePlayClient(cfg["pureplay"]["host"], cfg["pureplay"]["port"],
                                  cfg["pureplay"].get("client_name", "Tiger Voice Control"),
                                  os.path.join(base_dir, "token.json"),
                                  on_event=self.on_event, on_status=self.status)
        self.queue = None
        self.loop = None
        for name, combo in cfg["hotkeys"].items():
            keys.parse_combo(combo)   # fail fast on a typo in config.json

    # ---------- plumbing ----------
    def status(self, text):
        print(f"[Tiger] {text}")

    def submit_text(self, text, conf):
        """Called from the listener thread."""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, (text, conf))

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        asyncio.create_task(self.api.run_forever())
        while True:
            text, conf = await self.queue.get()
            await self.handle_text(text, conf)

    def units_distance(self, metres):
        if self.cfg.get("units", "yards") == "metres" or self.cfg.get("units") == "meters":
            return metres, "metres"
        return metres * M_TO_YD, "yards"

    # ---------- recognised speech ----------
    async def handle_text(self, text, conf):
        cmd = self.vocab.parse(text)
        if cmd is None:
            log.debug("Ignored: %r (%.2f)", text, conf)
            return
        min_conf = self.cfg.get("min_confidence", 0.55)
        if conf < min_conf:
            print(f"  heard '{text}' but not sure ({conf:.2f} < {min_conf}); ignoring")
            return
        if self.sleeping and cmd.action != "wake":
            return
        print(f"> {text}   ({conf:.2f})")
        handler = getattr(self, f"do_{cmd.action}", None)
        if handler is None:
            log.warning("No handler for %s", cmd.action)
            return
        try:
            await handler(cmd.arg)
        except ApiError as e:
            self.explain(e)
        except Exception:
            log.exception("Command failed: %s", text)
            self.speaker.say("Sorry, that didn't work.")

    def explain(self, e):
        if e.code == "disconnected":
            self.speaker.say("I'm not connected to Pureplay.")
        elif e.code == "not_ready" and e.blockers:
            self.speaker.say("Not right now, " + BLOCKER_WORDS.get(e.blockers[0], "the game isn't ready") + ".")
        elif e.code == "forbidden_scope":
            if self.api.is_read_only:
                # Paired read-only: the toggle can't fix this, only re-pairing can.
                self.status("Tiger is paired READ-ONLY. In Pureplay > Settings > Accessories, click "
                            "Remove next to Tiger Voice Control, close Tiger, delete token.json, "
                            "start Tiger again and choose 'Aim and club' before Allow.")
                self.speaker.say("I'm paired read only, so I can't change aim or club. "
                                 "In Pureplay's Accessories settings, remove me, delete token dot json, "
                                 "restart me, and choose aim and club when you approve.")
            else:
                self.status("Pureplay refused an aim/club change. In Settings > Accessories, turn on "
                            "'Let Apps Change Aim and Club'.")
                self.speaker.say("Pureplay won't let me change aim or club. "
                                 "Turn on Let Apps Change Aim and Club in the Accessories settings.")
        elif e.code == "not_allowed":
            self.speaker.say("Pureplay won't allow that right now.")
        else:
            log.info("API error: %s", e)
            self.speaker.say("Pureplay said no.")

    # ---------- helpers ----------
    async def press(self, name, confirm=True):
        combo = self.cfg["hotkeys"][name]
        if self.cfg.get("focus_game_before_keys", True) and not self.dry_run:
            await asyncio.to_thread(keys.focus_window, self.cfg.get("game_window_title", "Pureplay"))
        await asyncio.to_thread(keys.press, combo, 0.06, self.dry_run)
        if confirm:
            mode = self.cfg["voice"].get("confirm_hotkeys", "beep")
            if mode == "beep":
                self.speaker.beep()
            elif mode == "voice":
                self.speaker.say(name.replace("_", " "))

    async def active_player(self):
        snap = await self.api.snapshot()
        turn = snap.get("turn") or {}
        pid = turn.get("activeShooterId")
        players = snap.get("players") or []
        player = next((p for p in players if p.get("playerId") == pid), None)
        if player is None:
            player = next((p for p in players if p.get("isLocal")), None)
        return snap, player

    def need_control(self):
        if not self.api.connected.is_set():
            raise ApiError("disconnected")
        if not self.api.has_control:
            raise ApiError("forbidden_scope")

    async def set_club_type(self, club_type, prefix=""):
        snap, player = await self.active_player()
        if not player:
            raise ApiError("not_ready", blockers=["not_your_turn"])
        bag = player.get("bag") or []
        entry = next((b for b in bag if b.get("type") == club_type), None)
        if entry is None:
            self.speaker.say(f"No {club_spoken(club_type)} in the bag.")
            return
        if player.get("clubId") == entry["clubId"]:
            self.speaker.say(prefix + club_spoken(club_type))
            return
        res = await self.api.command("club.set", clubId=entry["clubId"])
        self.speaker.say(prefix + club_spoken(res.get("club") or club_type))

    # ---------- actions ----------
    async def do_hotkey(self, name):
        await self.press(name)

    async def do_club_set(self, club_type):
        if not self.api.has_control:
            if club_type == "Putter":
                return await self.press("putter")
            self.need_control()
        await self.set_club_type(club_type)

    async def do_club_step(self, direction):
        self.need_control()
        res = await self.api.command("club.next" if direction == "next" else "club.prev")
        self.speaker.say(club_spoken(res.get("club")))

    async def do_club_reset(self, _):
        self.need_control()
        res = await self.api.command("club.reset")
        self.speaker.say(club_spoken(res.get("club")))

    async def do_club_for(self, yards, prefix_distance=True):
        self.need_control()
        snap, player = await self.active_player()
        if not player:
            raise ApiError("not_ready", blockers=["not_your_turn"])
        if self.cfg.get("units") in ("metres", "meters"):
            yards = yards * M_TO_YD
        types = [b.get("type") for b in player.get("bag") or []]
        choice = pick_club_for(yards, self.cfg.get("carry_yards", {}), types)
        if not choice:
            self.speaker.say("Add your carry distances to the config file first.")
            return
        await self.set_club_type(choice)

    async def do_club_for_pin(self, _):
        snap, player = await self.active_player()
        if not player or player.get("distanceToHoleM") is None:
            raise ApiError("not_ready", blockers=["not_your_turn"])
        if player.get("lie") == "Green" or (player.get("hole") or {}).get("onGreen"):
            if self.api.has_control:
                return await self.set_club_type("Putter")
            return await self.press("putter")
        self.need_control()
        yards = player["distanceToHoleM"] * M_TO_YD
        types = [b.get("type") for b in player.get("bag") or []]
        choice = pick_club_for(yards, self.cfg.get("carry_yards", {}), types)
        if not choice:
            self.speaker.say("Add your carry distances to the config file first.")
            return
        dist, unit = self.units_distance(player["distanceToHoleM"])
        await self.set_club_type(choice, prefix=f"{spoken_number(dist)} out. ")

    async def do_aim_nudge(self, deg):
        self.need_control()
        res = await self.api.command("aim.nudge", deltaDeg=deg)
        applied = res.get("deltaDeg", deg)
        self.speaker.say(f"{'Left' if applied < 0 else 'Right'} {spoken_number(abs(applied))}")

    async def do_aim_pin(self, _):
        self.need_control()
        snap = await self.api.snapshot()
        pin = (snap.get("hole") or {}).get("pin")
        if not pin:
            raise ApiError("not_ready", blockers=["not_in_play"])
        await self.api.command("aim.set", target=pin)
        self.speaker.say("At the pin.")

    async def do_aim_reset(self, _):
        if self.api.has_control:
            await self.api.command("aim.reset")
            self.speaker.say("Aim reset.")
        else:
            await self.press("aim_reset")

    async def do_say_distance(self, _):
        snap, player = await self.active_player()
        if not player or player.get("distanceToHoleM") is None:
            self.speaker.say("I don't have a distance right now.")
            return
        m = player["distanceToHoleM"]
        if player.get("lie") == "Green" or (player.get("hole") or {}).get("onGreen"):
            self.speaker.say(f"{spoken_number(m * M_TO_FT)} feet.")
        else:
            d, unit = self.units_distance(m)
            self.speaker.say(f"{spoken_number(d)} {unit} to the pin.")

    async def do_say_score(self, _):
        snap, player = await self.active_player()
        if not player:
            self.speaker.say("There's no round in play.")
            return
        to_par = player.get("toPar")
        if to_par is None:
            score = "no score yet"
        elif to_par == 0:
            score = "even par"
        else:
            score = f"{spoken_number(abs(to_par))} {'over' if to_par > 0 else 'under'}"
        strokes = (player.get("hole") or {}).get("strokes") or 0
        hole = (snap.get("hole") or {}).get("number")
        extra = f" Hitting {spoken_number(strokes + 1)} on {spoken_number(hole)}." if hole else ""
        self.speaker.say(f"{player.get('name', 'You')}, {score}.{extra}")

    async def do_say_club(self, _):
        snap, player = await self.active_player()
        self.speaker.say(club_spoken(player.get("club")) if player else "No club yet.")

    async def do_lights(self, level):
        ha = self.cfg.get("home_assistant", {})
        if not ha.get("enabled"):
            self.speaker.say("Home Assistant isn't set up in my config.")
            return
        from .home_assistant import set_light
        try:
            await asyncio.to_thread(set_light, ha, level)
            self.speaker.beep()
        except Exception as e:
            log.warning("Home Assistant call failed: %s", e)
            self.speaker.say("I couldn't reach Home Assistant.")

    async def do_sleep(self, _):
        self.sleeping = True
        self.speaker.say(f"Going quiet. Say {self.vocab.wake_word} wake up to bring me back.")

    async def do_wake(self, _):
        self.sleeping = False
        self.speaker.say("I'm listening.")

    async def do_help(self, _):
        self.speaker.say("Just ask naturally. For example: give me a seven iron, aim a little left, "
                         "aim at the pin, what should I hit from one fifty, take a mulligan, "
                         "do a flyover, how far, or how am I doing.")

    # ---------- game events ----------
    async def on_event(self, name, data):
        ann = self.cfg.get("announce", {})
        ha = self.cfg.get("home_assistant", {})
        if name == "shot.ready_changed":
            sid = data.get("shotId")
            if data.get("ready") and sid and sid not in self.announced_shots and not self.sleeping:
                self.announced_shots.add(sid)
                if ann.get("your_turn") or ann.get("distance_on_turn"):
                    await self.announce_turn()
        elif name == "shot.completed" and ann.get("shot_result") and not self.sleeping:
            outcome = data.get("outcome")
            if outcome == "Holed":
                self.speaker.say("In the hole!")
            elif not data.get("isPutt") and data.get("carryM"):
                carry, unit = self.units_distance(data["carryM"])
                left = data.get("endDistToHoleM")
                msg = f"Carry {spoken_number(carry)}."
                if outcome in ("OB", "Water", "Lost"):
                    msg += f" {'Out of bounds' if outcome == 'OB' else outcome}."
                elif left:
                    if outcome == "Green":
                        msg += f" {spoken_number(left * M_TO_FT)} feet left."
                    else:
                        msg += f" {spoken_number(self.units_distance(left)[0])} to go."
                self.speaker.say(msg)
        elif name == "match.started":
            self.announced_shots.clear()
            if ha.get("enabled") and ha.get("auto_dim_on_round_start"):
                await self.do_lights("dim")
        elif name == "match.ended":
            if ha.get("enabled") and ha.get("auto_brighten_on_round_end"):
                await self.do_lights("bright")
        elif name == "context.invalidated":
            self.announced_shots.clear()

    async def announce_turn(self):
        ann = self.cfg.get("announce", {})
        try:
            snap, player = await self.active_player()
        except ApiError:
            return
        if not player:
            return
        parts = []
        if ann.get("your_turn") and len(snap.get("players") or []) > 1:
            parts.append(f"{player.get('name', 'Next player')}, you're up.")
        m = player.get("distanceToHoleM")
        if ann.get("distance_on_turn") and m:
            if player.get("lie") == "Green" or (player.get("hole") or {}).get("onGreen"):
                parts.append(f"{spoken_number(m * M_TO_FT)} feet.")
            else:
                d, unit = self.units_distance(m)
                parts.append(f"{spoken_number(d)} to the pin.")
        if parts:
            self.speaker.say(" ".join(parts))


# ---------------------------------------------------------------------------
def load_config(base_dir):
    with open(os.path.join(base_dir, "config.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Tiger - voice control for Pureplay")
    ap.add_argument("--type", action="store_true", help="type commands instead of using the mic")
    ap.add_argument("--dry-run", action="store_true", help="don't send any keystrokes")
    ap.add_argument("--list-mics", action="store_true", help="show microphones and exit")
    ap.add_argument("--list-windows", action="store_true", help="show window titles and exit")
    ap.add_argument("--debug", action="store_true", help="show everything the recogniser hears")
    ap.add_argument("--list-voices", action="store_true", help="show installed voices and exit")
    ap.add_argument("--say", metavar="TEXT", help="speak TEXT with the configured voice and exit")
    ap.add_argument("--voice", metavar="NAME", help="voice to use (overrides config.json)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("websockets").setLevel(logging.WARNING)

    if args.list_mics:
        from .audio import list_mics
        print("\n".join(list_mics()))
        return
    if args.list_voices:
        from .audio import list_voices
        print("\n".join(list_voices()))
        return
    if args.list_windows:
        for _, title in keys.list_windows():
            print(title)
        return

    if sys.platform == "win32":
        os.system("title Tiger Voice Control")
        if not args.type:
            # Only one listening copy at a time (e.g. if the sim launcher is run twice).
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            _mutex = kernel32.CreateMutexW(None, False, "Local\\TigerVoiceControl")
            if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
                print("Tiger is already running.")
                return
            main._mutex = _mutex                 # keep the handle alive

    cfg = load_config(base_dir)
    from .audio import Speaker, Listener
    v = cfg.get("voice", {})
    speaker = Speaker(v.get("enabled", True), v.get("rate", 190), v.get("volume", 1.0),
                      args.voice or v.get("name"))
    if args.say:
        speaker.say(args.say)
        speaker.wait_until_done()
        return
    tiger = Tiger(cfg, base_dir, speaker, dry_run=args.dry_run)
    stop = threading.Event()

    def start_input():
        if args.type:
            print(f"Type commands (e.g. '{tiger.vocab.wake_word} seven iron'). Ctrl+C to quit.")
            def typer():
                for line in sys.stdin:
                    line = " ".join(number_phrases(int(w))[0] if w.isdigit() and 0 < int(w) < 400 else w
                                    for w in line.strip().lower().replace(",", " ").split())
                    if line and not line.startswith(tiger.vocab.wake_word + " "):
                        line = f"{tiger.vocab.wake_word} {line}"
                    if line:
                        tiger.submit_text(line, 1.0)
            threading.Thread(target=typer, daemon=True).start()
        else:
            model = cfg["vosk_model"]
            if not os.path.isabs(model):
                model = os.path.join(base_dir, model)
            if not os.path.isdir(model):
                print(f"Speech model not found at {model}. Run setup.bat first.")
                sys.exit(1)
            mic = cfg.get("mic", {})
            def on_text(text, conf):
                if args.debug:
                    print(f"  (heard: '{text}' {conf:.2f})")
                tiger.submit_text(text, conf)
            listener = Listener(model, tiger.vocab.grammar(), on_text,
                                device=mic.get("device"), sample_rate=mic.get("sample_rate", 16000),
                                speaker=speaker)
            threading.Thread(target=listener.run, args=(stop,), daemon=True).start()
        print(f"Tiger is ready. Say '{tiger.vocab.wake_word}' then a command.")

    async def runner():
        start_input()
        await tiger.run()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        stop.set()
        print("Bye.")
