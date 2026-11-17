# Tiger reference

Say **"Tiger"** followed by a command. Speech is recognised offline on the CPU (Vosk), so it doesn't
touch the GPU or need the internet. Anything that doesn't start with "Tiger" and match a full command
is ignored, so talking about your 7 iron does nothing.

- **Aim and club** go through the Pureplay Accessory API: exact degrees, any club by name, aim at the
  pin, pick a club for a distance.
- **Everything else** presses the Pureplay hotkeys (mulligan, flyover, cameras, scorecard…), the same
  way JoyToKey does. JoyToKey can keep running alongside.
- **Callouts:** when a shot is set up, Tiger says who's up (in group play) and the distance.

## Setup (once)

1. Install Python 3.10+ from python.org if it isn't installed. Tick **Add python.exe to PATH**.
2. Copy this folder somewhere permanent, for example `C:\Tiger`.
3. Double-click **setup.bat**. It installs the packages, downloads the speech model and lists your mics.
4. In **config.json**, set `"device"` under `"mic"` to part of your mic's name, for example `"TONOR"`,
   or leave it `null` to use the Windows default mic.
5. In Pureplay, open **Settings > Accessories**:
   - **Allow apps from:** This PC
   - **Ask about new apps:** on (for the first connection)
   - **Let Apps Change Aim and Club:** on
   - Press Apply.
6. Start Pureplay, then **run_tiger.bat**. The first time, Pureplay shows an approval prompt for
   "Tiger Voice Control". Approve it **with aim and club control**. Tiger saves a token in `token.json`
   and won't ask again.

### Test before the mic arrives
`run_tiger.bat --type` lets you type commands instead of speaking (for example `seven iron` or
`aim left 3`, with the wake word optional). Add `--dry-run` to see which keys would be pressed
without pressing them.

### Start it with the sim
Add this line to your launcher .bat, after Pureplay starts:
```
start "Tiger" /min "C:\Tiger\run_tiger.bat"
```

## Commands

Start with **"Tiger"** and then ask naturally. Tiger listens for the words that matter and
ignores polite filler, so these all work the same:
"Tiger, seven iron" · "Tiger, give me a seven iron" · "Tiger, could you give me a seven iron please".

| What you want | Things you can say ("Tiger, …") |
|---|---|
| A club | give me a seven iron · can I get the driver · I'll hit a pitching wedge · let's go with a three wood · putter please |
| Club for a distance | what should I hit from one fifty · club for a hundred and twenty · what club for one oh five |
| Club for this shot | what club should I hit · what should I hit · club for the pin (putter on the green) |
| Pureplay's suggestion | suggest a club · reset the club |
| Step through the bag | next club · previous club · club up · club down |
| Nudge aim | aim left · aim a little right (1°) · aim a lot left (5°) · aim right three degrees · move it left ten |
| Aim at the cup | aim at the pin · aim at the flag · line me up on the flag |
| Reset aim | reset the aim |
| Mulligan | take a mulligan · mulligan · do over |
| Skip / fast forward | skip player · fast forward |
| Tee position | move the tee left · tee right |
| Cameras | do a flyover · fly to the ball · aim point · fly to the aim point · first person |
| Screens | show me the scorecard · heat map · green grid · ball trails · hud · weather · show FPS · full screen · shortcuts |
| Other | switch hands · mute |
| Questions | how far · what's the yardage · how am I doing · what club am I hitting |
| Lights (Home Assistant) | lights down · dim the lights · lights up |
| Tiger itself | go to sleep · wake up · help |

Plain left/right with no number nudges 2°. Numbers can be said the golf way ("one fifty",
"one oh five") or in full ("a hundred and fifty").

## Settings (config.json)

- **`carry_yards`**: your carry distance for each club, used by "club for…". Club names are
  `Driver`, `Wood3`, `Hybrid4`, `Iron7`, `PitchingWedge`, `GapWedge`, `SandWedge`, `LobWedge`.
  The numbers in it are placeholders, so replace them with yours.
- **`announce`**: `your_turn` and `distance_on_turn` are the callouts when a shot is set up.
  Set `shot_result` to `true` for "Carry 152. 18 to go." after each shot.
- **`voice.name`**: which Windows voice Tiger speaks with. Run `python tiger.py --list-voices` to see
  them, then put part of the name here (for example `"Zira"` or `"Mark"`). Try one first with
  `python tiger.py --voice Zira --say "Seven iron. One fifty to the pin."`
- **`voice.rate`**: speaking speed (about 180 is normal; 220 is brisk).
- **`voice.confirm_hotkeys`**: `"beep"`, `"voice"` (says the action) or `"none"`.
- **`min_confidence`**: raise it (e.g. 0.7) if Tiger acts on things you didn't say, lower it if it
  ignores you.
- **`hotkeys`**: change these if you rebind keys in Pureplay. Combos look like `"ctrl+m"`.
- **`units`**: `"yards"` or `"metres"`.
- **`game_window_title`**: Tiger brings the Pureplay window to the front before pressing keys. If keys
  don't land, run `python tiger.py --list-windows` and put part of Pureplay's window title here.
- **`home_assistant`**: set `enabled` to true, plus your URL, a long-lived access token (HA profile >
  Security) and the light entity. `auto_dim_on_round_start` dims the room when a round starts.

## Troubleshooting

- **"Approve … on the Pureplay screen" keeps appearing:** approve it within 60 seconds. If you
  removed Tiger in Settings > Accessories, delete `token.json` and restart.
- **"I don't have permission to change aim and club":** either *Let Apps Change Aim and Club* is
  off, or Tiger was approved read-only. Remove Tiger in Settings > Accessories, delete `token.json`,
  restart, and approve it with control.
- **It doesn't hear you:** check the mic with `python tiger.py --list-mics`, raise the mic level in
  Windows Sound settings, and run with `--debug` to see everything it hears.
- **Hotkeys don't work but aim/club do:** Pureplay probably wasn't the active window. See
  `game_window_title` above.
