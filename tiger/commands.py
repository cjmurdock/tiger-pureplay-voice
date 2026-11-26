"""Voice command understanding: builds the Vosk grammar and turns recognised text into actions.

Commands are matched by intent, not exact wording: after the wake word Tiger looks for the
words that matter ("seven iron", "aim", "left", "flyover"...) and ignores polite filler, so
"tiger seven iron", "tiger give me a seven iron" and "tiger could you give me a seven iron
please" all do the same thing.

Pure Python with no Windows or audio dependencies, so it can be tested anywhere.
"""
from dataclasses import dataclass, field

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
ONES_VAL = {w: i for i, w in enumerate(ONES)}
TENS_VAL = {w: i * 10 for i, w in enumerate(TENS) if w}
NUMBER_WORDS = set(ONES_VAL) | set(TENS_VAL) | {"hundred", "oh"}


def _under_100(n):
    if n < 20:
        return ONES[n]
    t, o = divmod(n, 10)
    return TENS[t] if o == 0 else f"{TENS[t]} {ONES[o]}"


def number_phrases(n):
    """All the ways a golfer might say n (1..399)."""
    if n < 100:
        return [_under_100(n)]
    h, rest = divmod(n, 100)
    out = []
    if rest == 0:
        out += [f"{ONES[h]} hundred"]
        if h == 1:
            out += ["a hundred"]
    else:
        r = _under_100(rest)
        out += [f"{ONES[h]} hundred {r}", f"{ONES[h]} hundred and {r}"]
        if h == 1:
            out += [f"a hundred {r}", f"a hundred and {r}"]
        # "one fifty", "two ten", "one oh five"
        out += [f"{ONES[h]} {r}"] if rest >= 10 else [f"{ONES[h]} oh {r}"]
    return out


def spoken_number(n):
    """How Tiger says a number: "one hundred fifty"; digits from 400 up."""
    n = int(round(n))
    return number_phrases(n)[0] if 0 < n < 400 else str(n)


def _small(tokens):
    """Value of a run like ["ninety", "five"] or ["twelve"]; None if not a valid < 100 number."""
    if not tokens:
        return 0
    if len(tokens) == 1:
        t = tokens[0]
        return ONES_VAL.get(t, TENS_VAL.get(t))
    if len(tokens) == 2 and tokens[0] in TENS_VAL and tokens[1] in ONES_VAL and 0 < ONES_VAL[tokens[1]] < 10:
        return TENS_VAL[tokens[0]] + ONES_VAL[tokens[1]]
    return None


def words_to_number(tokens):
    """Parse spoken numbers: "seven", "ninety five", "one fifty", "one oh five",
    "a hundred and twenty", "two hundred ten". Returns int or None."""
    toks = [t for t in tokens if t != "and"]
    if not toks:
        return None
    if "hundred" in toks:
        i = toks.index("hundred")
        head = toks[:i]
        h = 1 if head in ([], ["a"]) else _small(head)
        rest = _small(toks[i + 1:])
        if h is None or rest is None or not 0 < h < 10:
            return None
        return h * 100 + rest
    if len(toks) >= 2 and toks[0] in ONES_VAL and 0 < ONES_VAL[toks[0]] < 10:
        tail = toks[1:]
        if tail[0] == "oh" and len(tail) == 2 and tail[1] in ONES_VAL and ONES_VAL[tail[1]] < 10:
            return ONES_VAL[toks[0]] * 100 + ONES_VAL[tail[1]]
        rest = _small(tail)
        if rest is not None and rest >= 10:
            return ONES_VAL[toks[0]] * 100 + rest      # "one fifty"
    return _small(toks)


def find_number(tokens):
    """First spoken number in a token list (allows "a hundred")."""
    i = 0
    while i < len(tokens):
        start = i
        if tokens[i] == "a" and i + 1 < len(tokens) and tokens[i + 1] == "hundred":
            i += 1
        if tokens[i] in NUMBER_WORDS:
            j = i
            while j < len(tokens) and (tokens[j] in NUMBER_WORDS or
                                       (tokens[j] == "and" and j + 1 < len(tokens) and tokens[j + 1] in NUMBER_WORDS)):
                j += 1
            n = words_to_number(tokens[start:j])
            if n is not None:
                return n
            i = j
        else:
            i = start + 1
    return None


# Club types used by the Pureplay Accessory API, mapped to how they are spoken.
CLUB_WORDS = {"Driver": ["driver"], "Putter": ["putter"],
              "PitchingWedge": ["pitching wedge", "pitch wedge"],
              "GapWedge": ["gap wedge", "approach wedge"],
              "SandWedge": ["sand wedge"], "LobWedge": ["lob wedge"]}
for _n in range(2, 10):
    CLUB_WORDS[f"Wood{_n}"] = [f"{ONES[_n]} wood"]
    CLUB_WORDS[f"Hybrid{_n}"] = [f"{ONES[_n]} hybrid"]
for _n in range(1, 10):
    CLUB_WORDS[f"Iron{_n}"] = [f"{ONES[_n]} iron"]
CLUB_LOOKUP = {w: t for t, ws in CLUB_WORDS.items() for w in ws}


def club_spoken(club_type):
    words = CLUB_WORDS.get(club_type)
    return words[0] if words else (club_type or "unknown club")


def find_club(text):
    """Club type named in the text, or None. text is space-joined lowercase words."""
    padded = f" {text} "
    for phrase, ctype in CLUB_LOOKUP.items():
        if f" {phrase} " in padded:
            return ctype
    return None


# Hotkey intents: (phrases any of which triggers it, hotkey name from config.json).
# Checked in order, so longer / more specific phrases come first.
HOTKEY_INTENTS = [
    (["mulligan", "do over", "redo", "replay that"], "mulligan"),
    (["skip"], "skip_player"),
    (["fast forward", "speed up", "hurry up"], "fast_forward"),
    (["tee left", "tee to the left", "tee box left"], "tee_left"),
    (["tee right", "tee to the right", "tee box right"], "tee_right"),
    (["club up"], "club_up"),
    (["club down"], "club_down"),
    (["fly to aim point", "fly to the aim point"], "fly_to_aim_point"),
    (["aim point"], "aim_point"),
    (["fly to ball", "fly to the ball", "back to the ball", "go to the ball"], "fly_to_ball"),
    (["flyover", "fly over"], "flyover"),
    (["first person"], "first_person"),
    (["scorecard", "score card"], "scorecard"),
    (["green grid", "grid"], "green_grid"),
    (["heat map"], "heat_map"),
    (["trails", "tracer", "tracers"], "ball_trails"),
    (["hud", "heads up"], "hud"),
    (["weather", "wind"], "weather"),
    (["switch hands", "change hands", "left handed", "right handed"], "switch_hands"),
    (["mute", "sound on", "sound off", "turn the sound"], "mute"),
    (["fps", "frame rate"], "fps"),
    (["full screen"], "fullscreen"),
    (["shortcuts", "keyboard"], "keyboard_overlay"),
]

LITTLE = {"little", "bit", "touch", "hair", "smidge", "tad", "slightly"}
LOTS = {"lot", "way", "lots", "much", "bunch"}

# Polite / filler words Tiger understands but ignores. They are listed so the recogniser
# can hear them (and not mangle them into command words).
FILLERS = ("could you would you can you will you please give me a an the get i i'll i'd let's "
           "let have hand grab use want need like to hit hitting pull out my it now okay ok hey "
           "just thanks thank go with put on switch change set select we us be gonna going "
           "do what which how should is am are from at for this that there here some "
           "of yeah yes alright right left up down club clubs yards yard degrees degree "
           "aim move turn point me more show open close hide see bring").split()

# Example sentences fed to the recogniser so it learns natural word orders.
PREFIXES = ["", "give me a", "give me the", "could you give me a", "can you give me a",
            "can i get a", "can i have a", "let me get a", "let me have a", "i'll take a",
            "i'll hit a", "i'll hit the", "hand me a", "hand me the", "i want a", "i need a",
            "go with a", "go with the", "switch to", "change to", "pull out the", "grab the",
            "grab me a", "let's go", "use the", "put me on", "please"]


# Words that mean "this is about Tiger's voice" (so "switch to Linda" changes voice).
VOICE_CUES = {"voice", "voices", "switch", "change", "use", "try", "talk", "speak", "sound",
              "hear", "be", "like", "swap"}
TALK_WORDS = {"talk", "talking", "speak", "speaking", "voice", "speech", "say", "read"}

VOICE_EXAMPLES = ["next voice", "different voice", "another voice", "try another voice",
                  "change your voice", "change voices", "switch voices", "new voice",
                  "what voices do you have", "which voices do you have", "list the voices",
                  "list voices", "what voices are there", "what voice is this",
                  "talk faster", "talk slower", "speak faster", "speak slower",
                  "talk a little faster", "talk a little slower", "talk a bit faster",
                  "talk a bit slower", "slow down", "slow down a bit", "speed up your voice",
                  "speak up", "louder", "talk louder", "speak louder", "a little louder",
                  "quieter", "talk quieter", "speak quieter", "a little quieter", "softer",
                  "speak softer", "not so loud", "volume up", "volume down",
                  "turn your voice up", "turn your voice down", "turn up your voice",
                  "turn down your voice"]
SETTINGS_EXAMPLES = ["settings", "open settings", "open the settings", "open your settings",
                     "show settings", "show the settings", "show me the settings", "show me settings",
                     "bring up the settings", "bring up settings", "pull up the settings",
                     "go to settings", "settings please", "the settings",
                     "close settings", "close the settings", "hide settings", "hide the settings",
                     "close your settings", "shut the settings", "exit settings"]
VOICE_NAME_PREFIXES = ["", "switch to", "switch voice to", "switch the voice to", "change to",
                       "change voice to", "change your voice to", "change the voice to",
                       "use", "use the voice", "try", "let me hear", "talk like", "voice",
                       "be", "switch to the voice", "i want", "give me"]


def reserved_words():
    """Words Tiger's commands use, so they can't be voice names or the wake word."""
    return set(FILLERS) | set(CLUB_LOOKUP) | NUMBER_WORDS | LITTLE | LOTS | \
        {w for phrases, _ in HOTKEY_INTENTS for p in phrases for w in p.split()} | \
        {w for c in CLUB_LOOKUP for w in c.split()} | VOICE_CUES | TALK_WORDS | \
        {"settings", "setting", "voice", "voices", "louder", "quieter", "faster", "slower"}


# Everyday words that would wake Tiger by accident if used as the wake word.
COMMON_WORDS = {"hey", "hi", "ok", "okay", "yes", "yeah", "no", "nope", "golf", "shot", "ball",
                "nice", "good", "great", "hit", "swing", "club", "hole", "green", "par", "birdie",
                "bogey", "eagle", "the", "and", "but", "so", "well", "oh", "um", "uh", "man",
                "dude", "guys", "come", "look", "wow", "sorry", "thanks", "thank", "you", "me",
                "computer", "game", "play", "player", "turn", "caddie", "caddy", "pro", "coach", "buddy"}


def check_wake_word(word):
    """(error, warning) for a proposed wake word; error means it can't be used."""
    w = (word or "").strip().lower()
    if not w:
        return "Type a word.", None
    if " " in w or not w.isalpha():
        return "Use a single word with letters only (Tiger listens for one word).", None
    if w in reserved_words():
        return f"\"{w}\" is part of Tiger's commands, so it would get mixed up.", None
    if w in COMMON_WORDS:
        return None, f"\"{w}\" comes up a lot in normal talk, so Tiger may wake by accident."
    if len(w) < 4:
        return None, "Very short words are easy to say or hear by accident."
    return None, None


def voice_words(names):
    """{'linda': 'Linda', 'mark': 'Mark', ...} from voice names like those in Tiger Settings.

    Only the first word of each name is listened for; names that clash with command words
    (a voice called "Driver", say) are skipped so they can't steal a command.
    """
    reserved = reserved_words()
    out = {}
    for name in names:
        word = "".join(ch for ch in name.split()[0].lower() if ch.isalpha() or ch == "'") \
            if name.split() else ""
        if word and word not in reserved and word not in out:
            out[word] = name
    return out


@dataclass
class Command:
    action: str
    arg: object = None
    text: str = ""


@dataclass
class Vocabulary:
    wake_word: str = "tiger"
    examples: list = field(default_factory=list)
    voices: dict = field(default_factory=dict)     # spoken word -> voice name

    @classmethod
    def build(cls, wake_word="tiger", voice_names=()):
        v = cls(wake_word=wake_word.lower().strip(), voices=voice_words(voice_names))
        ex = v.examples
        ex += VOICE_EXAMPLES
        ex += SETTINGS_EXAMPLES
        for word in v.voices:
            for p in VOICE_NAME_PREFIXES:
                ex.append(f"{p} {word}".strip())
        clubs = list(CLUB_LOOKUP)
        for p in PREFIXES:
            for c in clubs:
                ex.append(f"{p} {c}".strip())
                ex.append(f"{p} {c} please".strip())
        for phrases, _ in HOTKEY_INTENTS:
            for ph in phrases:
                for p in ("", "please", "show me the", "can you", "could you", "let's see the",
                          "turn on the", "turn off the", "open the", "close the", "hide the",
                          "show the", "take a", "give me a", "i'll take a", "do a", "let's do a"):
                    ex.append(f"{p} {ph}".strip())
        for side in ("left", "right"):
            ex += [f"aim {side}", side, f"aim a little {side}", f"aim a bit {side}",
                   f"aim a lot {side}", f"move it {side}", f"move it a little {side}",
                   f"aim more {side}", f"a little more {side}", f"turn {side}", f"go {side}"]
            for n in range(1, 46):
                w = number_phrases(n)[0]
                ex += [f"aim {side} {w}", f"aim {side} {w} degrees", f"{w} degrees {side}",
                       f"aim {w} {side}", f"move it {side} {w}", f"{side} {w}"]
        ex += ["aim at the pin", "aim at the flag", "aim at the hole", "aim at the cup",
               "point me at the pin", "aim for the pin", "line me up on the flag",
               "reset aim", "reset the aim", "aim reset", "reset my aim",
               "next club", "previous club", "last club", "suggested club", "suggest a club",
               "reset club", "reset the club", "what club", "what club should i hit",
               "what should i hit", "which club should i use", "club for the pin",
               "how far", "how far is it", "how far to the pin", "how far is the pin",
               "what's the distance", "distance", "yardage", "what's the yardage",
               "how am i doing", "what's my score", "score", "what am i hitting",
               "what club am i hitting", "current club", "what club do i have",
               "lights down", "lights up", "dim the lights", "turn the lights down",
               "turn the lights up", "lights on", "lights off", "brighten the lights",
               "go to sleep", "stop listening", "wake up", "start listening", "help",
               "what can you do", "thanks", "thank you"]
        for n in range(20, 351):
            for w in number_phrases(n):
                ex += [f"club for {w}", f"club for {w} yards", f"what should i hit from {w}",
                       f"what club for {w}", f"i've got {w}", f"i have {w}", f"{w} yards"]
        return v

    def grammar(self):
        """Vosk grammar: example sentences behind the wake word, the filler vocabulary, and
        [unk] so ordinary conversation is not forced onto command words."""
        g = {f"{self.wake_word} {e}" for e in self.examples}
        g.update(FILLERS)
        g.add(self.wake_word)
        return sorted(g) + ["[unk]"]

    def parse(self, text):
        """Return a Command for recognised text, or None if it is not a wake-word command.
        The wake word may come after other speech ("nice shot tiger eight iron"); the last
        wake word that is followed by an understandable request wins."""
        words = [w for w in text.lower().split() if w != "[unk]"]
        for i in range(len(words) - 1, -1, -1):
            if words[i] == self.wake_word:
                cmd = interpret(words[i + 1:], self.voices)
                if cmd:
                    return cmd
        return None


def _has(text, *phrases):
    padded = f" {text} "
    return any(f" {p} " in padded for p in phrases)


def interpret(tokens, voices=None):
    """Map the words after the wake word to a Command, or None.

    voices: {spoken word: voice name} for the voices installed on this PC.
    """
    if not tokens:
        return None
    text = " ".join(tokens)
    toks = set(tokens)
    C = lambda a, arg=None: Command(a, arg, text)

    # The Tiger Settings window
    if toks & {"settings", "setting"}:
        if toks & {"close", "hide", "exit", "shut", "dismiss"}:
            return C("settings_close")
        return C("settings_open")

    # Tiger's own voice: which one, speed, volume
    voice_cmd = _interpret_voice(text, tokens, toks, voices or {})
    if voice_cmd:
        return C(*voice_cmd)

    # program control
    if _has(text, "go to sleep", "stop listening"):
        return C("sleep")
    if _has(text, "wake up", "start listening"):
        return C("wake")
    if _has(text, "help", "what can you do"):
        return C("help")

    # lights (Home Assistant)
    if "lights" in toks or "light" in toks:
        if toks & {"down", "dim", "off", "darker"}:
            return C("lights", "dim")
        if toks & {"up", "on", "bright", "brighten", "brighter"}:
            return C("lights", "bright")

    # hotkeys whose words overlap with aim/club words go first
    for phrases, name in HOTKEY_INTENTS[:10]:     # through "aim point" / "fly to ball"
        if _has(text, *phrases):
            return C("hotkey", name)

    # aim
    if _has(text, "reset aim", "reset the aim", "aim reset", "reset my aim"):
        return C("aim_reset")
    if toks & {"pin", "flag", "hole", "cup"} and toks & {"aim", "at", "point", "line", "on"} \
            and not toks & {"far", "distance", "yardage", "club", "hit"}:
        return C("aim_pin")
    side = "left" if "left" in toks else "right" if "right" in toks else None
    if side and not find_club(text) and not toks & {"handed", "hands", "hand"}:
        sign = -1 if side == "left" else 1
        n = find_number(tokens)
        if n is None or not 1 <= n <= 45:
            n = 1 if toks & LITTLE else 5 if toks & LOTS else 2
        return C("aim_nudge", sign * n)

    # club for a distance
    n = find_number(tokens)
    club = find_club(text)
    if n is not None and n >= 20 and not club and \
            (toks & {"club", "hit", "for", "from", "yards", "yard", "got", "have"}):
        return C("club_for", n)

    # questions about the club
    if _has(text, "what am i hitting", "what club am i", "current club", "what club do i have",
            "which club am i"):
        return C("say_club")
    if (toks & {"what", "which"} and toks & {"club", "hit"}) or _has(text, "club for the pin"):
        return C("club_for_pin")
    if _has(text, "next club"):
        return C("club_step", "next")
    if _has(text, "previous club", "last club"):
        return C("club_step", "prev")
    if (toks & {"suggest", "suggested", "recommend", "recommended", "reset"}) and "club" in toks:
        return C("club_reset")

    # pick a club
    if club:
        return C("club_set", club)

    # information
    if _has(text, "how far", "distance", "yardage"):
        return C("say_distance")
    if _has(text, "how am i doing", "my score", "what's the score") or text == "score":
        return C("say_score")

    # remaining hotkeys
    for phrases, name in HOTKEY_INTENTS[10:]:
        if _has(text, *phrases):
            return C("hotkey", name)
    return None


def _interpret_voice(text, tokens, toks, voices):
    named = [voices[t] for t in tokens if t in voices]
    if named and (toks & VOICE_CUES or len(tokens) == 1):
        return ("voice_set", named[-1])
    if _has(text, "what voices", "which voices", "list voices", "list the voices",
            "what voice is this", "voices do you have", "voices are there"):
        return ("voice_list", None)
    if (toks & {"voice", "voices"}) and toks & {"next", "different", "another", "new", "change",
                                                "switch", "other"} \
            and not toks & {"up", "down", "faster", "slower", "louder", "quieter"}:
        return ("voice_next", None)
    talking = bool(toks & TALK_WORDS)
    if (toks & {"faster", "quicker"} and talking) or _has(text, "speed up your voice"):
        return ("voice_speed", 1)
    if (toks & {"slower"} and talking) or _has(text, "slow down"):
        return ("voice_speed", -1)
    if toks & {"louder"} or _has(text, "speak up", "volume up", "turn your voice up",
                                 "turn up your voice"):
        return ("voice_volume", 1)
    if toks & {"quieter", "softer"} or _has(text, "not so loud", "volume down",
                                            "turn your voice down", "turn down your voice"):
        return ("voice_volume", -1)
    return None


def pick_club_for(distance_yards, carries, bag_types):
    """Choose the club whose carry is closest to the target without being more than 5 yards short.

    carries: {club_type: carry_yards}; bag_types: club types actually in the bag.
    """
    options = [(c, carries[c]) for c in bag_types if c in carries and c != "Putter"]
    if not options:
        return None
    long_enough = [o for o in options if o[1] >= distance_yards - 5]
    if long_enough:
        return min(long_enough, key=lambda o: o[1])[0]
    return max(options, key=lambda o: o[1])[0]
