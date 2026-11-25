# Tiger reference

Say **"Tiger"** followed by a command. Speech is recognised offline on the CPU (Vosk), so it doesn't
touch the GPU or need the internet. Anything that doesn't start with "Tiger" and match a full command
is ignored, so talking about your 7 iron does nothing.

- **Aim and club** go through the Pureplay Accessory API: exact degrees, any club by name, aim at the
  pin, pick a club for a distance.
- **Everything else** presses the Pureplay hotkeys (mulligan, flyover, cameras, scorecard…), the same
  way JoyToKey does. JoyToKey can keep running alongside.
- **Callouts:** when a shot is set up, Tiger says who's up (in group play) and the distance.

> **Already using Tiger? To update:** open **Tiger Settings** and go to the **Updates** tab, then press **Update now** (or double-click **`update.bat`** in your Tiger folder). It downloads the latest version from GitHub, closes and restarts Tiger for you, and keeps your settings (`config.json`), your Pureplay pairing (`token.json`) and the speech model. Any new settings are added with their defaults, and the replaced files are backed up in `backups\`.
>
> **No Updates tab yet?** (copies from before 24 November 2026) Download **[Tiger_Update.bat](https://github.com/cjmurdock/tiger-pureplay-voice/releases/latest/download/Tiger_Update.bat)** (also on the [Releases page](https://github.com/cjmurdock/tiger-pureplay-voice/releases)) and double-click it. Running it from your Downloads folder is fine. It finds your Tiger folder, closes Tiger, updates it with the same rules, and starts Tiger again. If Windows warns about an unknown app, choose *More info*, then *Run anyway*. After that, use the Updates tab. <details><summary>Prefer to do it by hand?</summary>Close Tiger, download the ZIP (**Code > Download ZIP** on the GitHub page), open the `tiger-pureplay-voice-main` folder inside it, and copy **everything in it except `config.json`** into your Tiger folder, choosing *Replace* when Windows asks. Don't delete your old folder first: the speech model in `models\` isn't in the download. You don't need to run `setup.bat` again.</details>

## Setup (once)

1. Install Python 3.10+ from python.org if it isn't installed. Tick **Add python.exe to PATH**.
2. Copy this folder somewhere permanent, for example `C:\Tiger`.
3. Double-click **setup.bat**. It installs the packages, downloads the speech model and lists your mics.
4. Double-click **Tiger Settings.bat** and pick your mic on the Microphone tab (or, in **config.json**,
   set `"device"` under `"mic"` to part of your mic's name, for example `"TONOR"`; `null` means the
   Windows default mic).
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
| Club for this shot | what club should I hit · what should I hit · club for the pin (putter on the green). Uses Pureplay's suggested club from the player's own bag when club suggestion is on |
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
| Tiger's voice | switch to Linda · use Mark · change your voice to Richard · let me hear Zira · next voice · what voices do you have |
| Voice speed / volume | talk faster · talk slower · slow down · speak up · louder · quieter · not so loud |
| Settings window | settings · open settings · show me the settings · close settings |
| Tiger itself | go to sleep · wake up · help |

Voice names are the ones installed on the PC (Tiger reads them at startup). Voice, speed and volume
changes are saved to config.json, so they stick. Speed moves one step and volume 10% at a time.

Plain left/right with no number nudges 2°. Numbers can be said the golf way ("one fifty",
"one oh five") or in full ("a hundred and fifty").

## Tiger Settings window

Say **"Tiger, open settings"**, or double-click **Tiger Settings.bat** (or run
`python tiger.py --settings`). "Tiger, close settings" closes it and puts Pureplay back in front.

- **Voice:** choose **Windows voices** (built in) or **Azure voices** (Microsoft's neural voices;
  see *Azure voices* below). Double-click or press **Preview** to hear one with the line in the box,
  then **Use this voice**. **Speed** and **Volume** save as you move them.
- **Microphone:** pick the mic, talk and watch the level bar, then **Use this microphone**. The
  slider below it is `min_confidence`.
- **Distances:** backup carry for each club (`carry_yards`), used only when Pureplay's club
  suggestion is off or you ask about a distance other than the one you have. Blank means the club
  isn't in your bag.
- **Players:** how Tiger says each Pureplay player's name (`player_names`), e.g. "cjmurdock" → "Cameron"
  in "you're up" and the score. Names appear once Tiger has seen them; **Test** says "<name>, you're up."
- **Status:** whether Tiger is running, how it's paired with Pureplay, **Re-pair Tiger**, and
  buttons to open the Tiger folder and config.json. **Start Tiger** runs `run_tiger.bat` if it isn't
  running.
- **Updates:** checks GitHub when the window opens ("Updates (new)" on the tab means there's one).
  **Update now** closes Tiger, installs the update (keeping config.json, token.json and the speech
  model, and adding any new settings with their defaults), starts Tiger again, and saves the
  replaced files in `backups\`. `update.bat` does the same from a command window.

Everything is saved to config.json straight away, changing only that setting, with the previous file
kept as `config.backup.json`. A running Tiger checks config.json every second and uses the new voice
or mic without restarting (the wake word still needs a restart). If config.json has a typo, Tiger
keeps its last good settings and the window shows where the mistake is.

## Azure voices

Microsoft's Azure neural voices are much more natural than the Windows ones. Setup (about 10 minutes):

1. Create a free account at azure.microsoft.com (a card is asked for to verify you; the free tier
   doesn't charge).
2. In portal.azure.com: **Create a resource** → search **Speech** → create it with any resource group,
   a region near you (e.g. Canada Central, West US 2) and the **Free F0** pricing tier.
3. Open it → **Keys and Endpoint** → copy **KEY 1** and the **Location/Region** (e.g. `canadacentral`).
4. Tiger Settings → Voice → **Azure voices** → paste key and region → **Connect**.
5. Pick a voice → **Preview** → **Download voice library** → **Use this voice**.

**The voice library:** every sentence Tiger can say (fixed replies, club names, distances 1–600,
aim 1–45°, scores, "<name>, you're up." for each player…, about 4,000 sentences and 90,000 characters)
saved as WAV files in `voices\azure\<voice>\speed<step>\`, so lines play instantly and offline.
Downloading asks Azure for 40 sentences at a time with long pauses between them and cuts the audio at
the pauses. Each voice and speed has its own library (volume is applied on the PC). A line that isn't
in the library is fetched the first time it's said (3-second limit) and kept; if Azure can't be reached
or the key is wrong, Tiger says it with the Windows voice instead and says why once in its window. New
player names are fetched in the background the first time they're seen. The free F0 tier covers
500,000 characters a month of the regular neural voices (HD voices aren't included). `voices\` is kept
by updates and isn't on GitHub. Voices with a library can be chosen by voice too ("Tiger, switch to
Liam"); Tiger reads that list when it starts.

## Settings (config.json)

- **`carry_yards`**: your carry distance for each club. Only a backup: with Pureplay's club
  suggestion on, "what club should I hit" (and "what should I hit from N" when N is the distance you
  have) uses Pureplay's suggestion from the player's own bag. These numbers are used for other
  distances and when suggestion is off. Club names are
  `Driver`, `Wood3`, `Hybrid4`, `Iron7`, `PitchingWedge`, `GapWedge`, `SandWedge`, `LobWedge`.
  The numbers in it are placeholders, so replace them with yours.
- **`announce`**: `your_turn` and `distance_on_turn` are the callouts when a shot is set up.
  Set `shot_result` to `true` for "Carry 152. 18 to go." after each shot.
- **`voice.name`**: which Windows voice Tiger speaks with (`null` for the Windows default). Easiest
  in Tiger Settings. From the command line: `python tiger.py --list-voices`, then put the name here
  (for example `"Zira"` or `"Mark"`), and try one with
  `python tiger.py --voice Zira --say "Seven iron. One fifty to the pin."` If the named voice isn't
  installed, Tiger uses the Windows default and says so in its window.
- **`voice.rate`**: speaking speed (about 180 is normal; 220 is brisk).
- **`voice.volume`**: 0.1 to 1.0.
- **`voice.engine`**: `"windows"` or `"azure"`; **`voice.azure_voice`**: the Azure voice id (e.g.
  `"en-CA-LiamNeural"`); **`azure.key`**, **`azure.region`**: your Speech resource's key and region.
  The key is private: don't share your config.json.
- **`player_names`**: `{"Pureplay name": "name to say"}`, e.g. `{"cjmurdock": "Cameron"}`.
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
- **"I'm paired read only" / a "Read only" tag next to Tiger in Settings > Accessories:** Tiger was
  approved read-only, so it can read the game (distance, score) but not change aim or club. Click
  **Remove** next to it in Pureplay's Settings > Accessories, then press **Re-pair Tiger** on the
  Status tab of Tiger Settings and choose **Aim and club** before **Allow**. (By hand: close Tiger,
  delete `token.json`, start Tiger again.) Nothing extra needs installing, because the
  API is built into Pureplay.
- **"Pureplay won't let me change aim or club":** Tiger has control permission but *Let Apps
  Change Aim and Club* is off. Turn it on in Settings > Accessories.
- **Tiger Settings doesn't open:** run the Python installer again, choose **Modify** and tick
  **tcl/tk and IDLE**.
- **It doesn't hear you:** watch the level bar on the Microphone tab of Tiger Settings, check the mic
  with `python tiger.py --list-mics`, raise the mic level in
  Windows Sound settings, and run with `--debug` to see everything it hears.
- **Hotkeys don't work but aim/club do:** Pureplay probably wasn't the active window. See
  `game_window_title` above.
