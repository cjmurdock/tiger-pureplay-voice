# Tiger 🐯⛳ Voice control for Pureplay golf

Say **"Tiger"** and ask naturally, and your Pureplay golf simulator does it:

> "Tiger, give me a seven iron." · "Tiger, aim a little left." · "Tiger, what should I hit from one fifty?" · "Tiger, take a mulligan." · "Tiger, do a flyover." · "Tiger, how far?"

- **Offline:** speech recognition runs on the CPU (Vosk), so it doesn't use the graphics card or the internet.
- **Precise aim and club control** through the official [Pureplay Accessory API](https://github.com/PureplayGolf/Pureplay-Accessory): pick any club by name, nudge aim by exact degrees, aim straight at the pin, or pick a club for a distance from your own carry numbers.
- **Every Pureplay hotkey by voice:** mulligan, skip, flyover, cameras, scorecard, heat map, green grid and more.
- **Talks back:** confirms commands and calls out "you're up, 150 to the pin" when it's your shot.
- **Safe around conversation:** nothing happens unless you say "Tiger" first, so talking about your 7 iron with friends is fine.
- **Tiger Settings window:** pick the voice (with a preview), speed and volume, choose the mic with a live level meter, enter your carry distances, and check the Pureplay pairing. A running Tiger picks up changes straight away, so there's no restart. You can also change the voice by voice: "Tiger, switch to Linda", "Tiger, talk faster".

## Get it

1. Click the green **Code** button above, then **Download ZIP**. You can also use the **Releases** page if there is one.
2. Unzip it to `C:\Tiger`.
3. Follow **[docs/Tiger_Setup_Guide.pdf](docs/Tiger_Setup_Guide.pdf)**. It takes about 10 minutes.

**Quick version:**
1. Install Python 3.10+ from python.org and tick **Add python.exe to PATH**.
2. Double-click `setup.bat`.
3. In Pureplay, go to **Settings > Accessories**. Set **Allow apps from** to This PC and turn **Let Apps Change Aim and Club** on.
4. Double-click `Tiger Settings.bat` and pick your microphone (and a voice, and your carry distances if you like).
5. Double-click `run_tiger.bat`. In Pureplay, choose **Aim and club**, then **Allow**. (Not **Read only**: that only lets Tiger read the game, so club and aim commands won't work.)
6. Say *"Tiger, give me a seven iron."*

## Troubleshooting: "Read only" / "no permission"

If Tiger can tell you the distance but says it doesn't have permission to change club or aim, and **Settings > Accessories** shows a **Read only** tag next to Tiger Voice Control, Tiger was approved read-only. There's nothing extra to install, because the Accessory API is built into Pureplay. To fix it, re-pair Tiger:

1. Close Tiger.
2. In Pureplay, open **Settings > Accessories** and click **Remove** next to Tiger Voice Control.
3. Delete `token.json` in your Tiger folder.
4. Start Tiger again. When Pureplay asks, choose **Aim and club**, then **Allow**.

The tag disappears and club and aim commands work. The **Status** tab in Tiger Settings has a **Re-pair Tiger** button that does steps 1, 3 and 4 for you (you still click Remove in Pureplay). More fixes are in the [setup guide](docs/Tiger_Setup_Guide.pdf).

## Documentation

| | |
|---|---|
| [Setup guide (PDF)](docs/Tiger_Setup_Guide.pdf) | Install, settings, troubleshooting |
| [Voice commands (PDF)](docs/Tiger_Voice_Commands.pdf) | Everything you can say |
| [Reference](docs/REFERENCE.md) | Full command table, every `config.json` setting, command-line options |

## Requirements

- Windows PC running Pureplay, with the Accessory API enabled
- A USB microphone near the hitting area. A 360° conference mic such as the TONOR G11 works well.
- Speakers
- Python 3.10 or newer

## How it works

`tiger/commands.py` understands what you asked. `tiger/settings_window.py` is the Tiger Settings window, and `tiger/config_store.py` saves config.json safely and passes status between Tiger and the window. `tiger/pureplay_api.py` talks to the Pureplay Accessory API for aim and club. `tiger/keys.py` presses Pureplay's hotkeys for everything the API doesn't cover. `tiger/audio.py` handles the microphone, Vosk and the Windows voice.

Ideas and bug reports are welcome. Please open an issue.

## License

MIT. See [LICENSE](LICENSE). The speech model that `setup.bat` downloads (Vosk small English) is Apache 2.0.
Tiger is a community project and isn't made by Pureplay.
