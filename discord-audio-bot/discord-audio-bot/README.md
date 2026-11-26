# Discord Music Presence

A small Windows companion that shows the currently playing track in your personal Discord profile. It reads Windows media sessions, so compatible MP3 players and Telegram Desktop can provide the track details without this program being a Discord bot.

## What it does

- Reads the title, artist, album, playback state, and thumbnail from the current Windows media session.
- Publishes the title and artist to your Discord Rich Presence as a **Listening** activity.
- Uses the media thumbnail for the profile artwork. BMP artwork is converted to JPEG or PNG.
- If no thumbnail is available, searches Apple's public music catalogue and uses a cover only when both the title and artist match.
- Checks for changed playback every five seconds by default. Set `POLL_SECONDS` in `.env` to change this.
- Writes detailed diagnostics to `music_presence.log` and shows Windows notifications for connection success and errors.
- Runs without a console window and can start when you sign in to Windows.

## What it sends

The audio file is never uploaded. To display a local cover on other people's Discord clients, the program uploads **only the image** to a public temporary image host and gives Discord its URL. Litterbox is tried first (links expire after 72 hours); Uguu is the fallback (links expire after 3 hours). Anyone who has a link can view the cover until it expires.

The program uses your Discord **Application ID**, which is public. It does not use a bot token, Client Secret, Discord password, or user-account token.

## Install and configure

1. Install Python 3.9 or newer. In the Python installer, enable **Add Python to PATH**.
2. Install the Discord desktop app and sign in to the account whose profile should show the music.
3. In the Discord Developer Portal, create an application. On **General Information**, copy **Application ID**. You do not need to create a bot.
4. Double-click `setup.bat`. It installs dependencies and creates `.env` if needed. It also adds a shortcut to the current Windows user's Startup folder.
5. Open `.env` and put the ID after `DISCORD_CLIENT_ID=`. Save and close it.
6. Double-click `start.bat` to run the companion hidden now. On future Windows sign-ins it starts automatically.
7. Play a track in an app that exposes a Windows media session. Discord must be running on the same computer.

`start_hidden.vbs` launches Python without a console. `install_startup.vbs` creates the Windows Startup shortcut. You can run `install_startup.vbs` again to recreate the shortcut.

## Notifications and logs

- **Connected successfully:** Discord is connected. Start playback to show music in your profile.
- **Discord is not running:** Open the Discord desktop app and sign in. The companion retries automatically.
- **Settings error:** Check that `DISCORD_CLIENT_ID` in `.env` contains the Application ID, not the Public Key or a bot token.
- **Rich Presence or connection error:** Check Discord and your internet connection, then read `music_presence.log` next to `audio_bot.py`.
- **No music activity:** The player may be paused, or it may not expose a Windows media session.
- **No cover / default application icon:** Windows may not have provided a thumbnail, neither image host may have accepted it, or the online catalogue may not have an exact title-and-artist match.

Error notifications are rate-limited so they do not appear every few seconds. The log can contain repeated connection attempts while Discord is closed.

## Troubleshooting

| Message or symptom | Fix |
|---|---|
| `Python was not found` | Reinstall Python and enable **Add Python to PATH**. Then run `setup.bat` again. |
| `Could not find start_hidden.vbs` | Keep the `.vbs` files in the same folder as `audio_bot.py`; run `setup.bat` from the extracted project folder. |
| `Set DISCORD_CLIENT_ID` / settings error | Copy **Application ID** from Developer Portal -> General Information into `.env`. Do not use the Public Key. |
| `Discord desktop app is not available` | Open Discord for Windows, sign in, and leave it running. The web app cannot receive local Rich Presence. |
| `ModuleNotFoundError` | Run `setup.bat` to install packages. |
| Dependency installation failed | Check your internet connection and Python installation, then run `setup.bat` again. |
| No Windows notifications appear | Run `setup.bat` so `winotify` is installed, then enable notifications for desktop apps in Windows Settings -> System -> Notifications. Diagnostics are still written to `music_presence.log`. |
| `Could not connect to Discord Rich Presence` | Check that the Application ID is correct and Discord is open. See `music_presence.log`. |
| `Windows media session has no thumbnail` | The player did not expose the embedded artwork to Windows. Try another player that publishes media metadata. |
| `Could not read the player's embedded cover` | The player's thumbnail stream was unavailable or invalid. Check `music_presence.log`; the public catalogue is used as a fallback. |
| `Could not convert the embedded BMP cover` | The BMP file may be damaged or too large. Try a smaller cover or a player that exposes JPEG/PNG artwork. |
| `Could not publish cover to Litterbox` | The temporary host may be unavailable. The program tries Uguu automatically. |
| `Could not publish cover to Uguu` | Both temporary hosts may be unavailable or blocked by the network. The public catalogue is the fallback. |
| `The player thumbnail is not a supported image format` | The media session supplied an unsupported or malformed image. |
| `No track appears` | Start or resume playback in an app that provides a Windows media session. |
| `The app starts twice` | Remove duplicate `Discord Music Presence` entries from the Startup folder and run `setup.bat` once. |

## Antivirus and Windows Security

Some security products may warn about this project because it uses Python in the background, runs a `.vbs` launcher, creates a Startup shortcut, and makes web requests to publish cover images. Those behaviors are explained above, but a warning should still be checked: a false positive is possible, and this README alone cannot verify a quarantined file.

Do not turn off antivirus or add a broad folder exclusion to make the warning disappear. Check the alert's file path and detection name, scan the project with Windows Security, and inspect the two `.vbs` files. If a security product blocks a file, follow that product's review process and only restore it if you trust the source and the detected file matches this project.

## Stop or disable auto-start

- To stop the current background process, open Task Manager and end the `pythonw.exe` process running `audio_bot.py`.
- To disable automatic startup, delete `Discord Music Presence.lnk` from the Windows Startup folder, or turn it off under **Settings -> Apps -> Startup**.
- Closing Discord also prevents the activity from appearing; the companion will retry until Discord is opened again.

This project is a local Rich Presence helper, not a bot. Discord activity sharing must be enabled in your Discord privacy settings.
