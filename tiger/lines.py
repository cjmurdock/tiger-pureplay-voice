"""Everything Tiger can say, as the separate sentences it's built from.

Tiger's replies are short sentences joined together ("Cameron, you're up." + "One hundred fifty
to the pin."). A downloaded voice library (see voice_library.py) stores one clip per sentence,
and split_sentences() cuts a reply into the same pieces when it's spoken, so every reply can be
played from clips recorded in advance.

When a new reply is added to app.py, add its sentences here too, or the first time it's said it
will be fetched online (and saved) instead of coming from the library.
"""
import re

from .commands import CLUB_WORDS, club_spoken, spoken_number

_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text):
    return [s.strip() for s in _SPLIT.split(text.strip()) if s.strip()]


def normalize(sentence):
    """The key a clip is stored under: same words, ignoring case and spacing."""
    return " ".join(sentence.lower().split())


def _numbers(top):
    """1..top, most-used golf distances first, so a half-finished download covers the most."""
    first = [n for n in range(100, 251) if n <= top]
    rest = [n for n in range(1, top + 1) if n not in set(first)]
    return first + rest


FIXED = [
    "I couldn't save that.", "Check config dot json.", "Sorry, that didn't work.",
    "I'm not connected to Pureplay.", "Pureplay won't allow that right now.", "Pureplay said no.",
    "I'm paired read only, so I can't change aim or club.",
    "In Pureplay's Accessories settings, remove me, delete token dot json, restart me, and choose "
    "aim and club when you approve.",
    "Pureplay won't let me change aim or club.",
    "Turn on Let Apps Change Aim and Club in the Accessories settings.",
    "Add your carry distances in Tiger Settings first.",
    "Turn on club suggestion in Pureplay, or add your distances in Tiger Settings.",
    "At the pin.", "Aim reset.", "I don't have a distance right now.", "There's no round in play.",
    "No club yet.", "Home Assistant isn't set up in my config.", "I couldn't reach Home Assistant.",
    "I'm listening.", "This is the only voice on this PC.", "I can't see the voices on this PC.",
    "That's as fast as I go.", "That's as slow as I go.", "Faster.", "Slower.",
    "That's as loud as I go.", "That's as quiet as I go.", "Louder.", "Quieter.",
    "Here are the settings.", "I couldn't open the settings.", "Opening settings.",
    "The settings aren't open.", "Closing settings.", "In the hole!", "Out of bounds.", "Water.",
    "Lost.", "Just ask naturally.",
    "For example: give me a seven iron, aim a little left, aim at the pin, what should I hit from "
    "one fifty, take a mulligan, do a flyover, how far, how am I doing, or talk faster.",
    "You're up.",
]
BLOCKERS = ["the ball's still moving", "there's no round in play", "the game is between phases",
            "nobody is up", "the game is waiting on a ruling",
            "turn on Let Apps Change Aim and Club in Pureplay's Accessories settings",
            "the game isn't ready"]


def repertoire(cfg, player_names=(), voice_names=(), max_distance=600):
    """Every sentence Tiger can say with these settings, most useful first, without repeats."""
    units = "metres" if cfg.get("units") in ("metres", "meters") else "yards"
    wake = cfg.get("wake_word", "tiger")
    clubs = [club_spoken(t) for t in CLUB_WORDS]
    out = []
    add = out.append

    for s in FIXED:
        add(s)
    for b in BLOCKERS:
        add(f"Not right now, {b}.")
    add("Going quiet.")
    add(f"Say {wake} wake up to bring me back.")
    for c in clubs:
        add(c)
        add(f"No {c} in the bag.")
    for name in (cfg.get("hotkeys") or {}):
        add(name.replace("_", " "))
    for name in player_names:
        add(f"{name}, you're up.")
    for n in _numbers(max_distance):
        w = spoken_number(n)
        add(f"{w} to the pin.")
        add(f"{w} out.")
        add(f"{w} {units} to the pin.")
    for n in _numbers(max_distance):
        w = spoken_number(n)
        add(f"Carry {w}.")
        add(f"{w} to go.")
    for n in range(1, 151):
        w = spoken_number(n)
        add(f"{w} feet.")
        add(f"{w} feet left.")
    for d in range(1, 46):
        w = spoken_number(d)
        add(f"Left {w}")
        add(f"Right {w}")
    scores = ["even par", "no score yet"] + \
        [f"{spoken_number(n)} {side}" for n in range(1, 41) for side in ("over", "under")]
    for name in list(player_names) + ["You"]:
        for sc in scores:
            add(f"{name}, {sc}.")
    for stroke in range(1, 16):
        for hole in range(1, 19):
            add(f"Hitting {spoken_number(stroke)} on {spoken_number(hole)}.")
    for v in voice_names:
        add(f"This is {v}.")

    seen, result = set(), []
    for s in out:
        for part in split_sentences(s):
            k = normalize(part)
            if k not in seen:
                seen.add(k)
                result.append(part)
    return result
