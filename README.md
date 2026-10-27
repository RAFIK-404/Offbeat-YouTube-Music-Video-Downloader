# Offbeat

**A simple YouTube music and video downloader for Windows.**

**[Download EXE only — Windows x64 (13.6 MB)](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/releases/download/v1.3.1-beta.1/Offbeat-1.3.1-Windows-x64.exe)** · [View release](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/releases/tag/v1.3.1-beta.1)

Open the EXE, choose a download folder, and let first-time setup finish. No Python installation or source ZIP is required.

[![Tests](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/actions/workflows/tests.yml/badge.svg)](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/actions/workflows/tests.yml)

Download videos, music, and full playlists in a dark desktop app. Save several files at once, skip duplicates, and keep your favorite playlists ready for their next update.

![Offbeat's dark desktop interface](https://github.com/user-attachments/assets/32042bd1-c686-4129-a212-46a8bf08aa68)

<details>
<summary>See automatic first-time setup</summary>

![Offbeat downloads and verifies its tools automatically](https://github.com/user-attachments/assets/364d9831-fe77-4365-878d-5a411c2df41e)

</details>

**Public beta · Windows x64 · Python + pywebview · Powered by yt-dlp and FFmpeg**

## What it does

- **Music and video:** export MP3 at 128, 192, or 320 kbps, or MP4 up to the source's available quality.
- **Parallel downloads:** run up to six transfers at once; three is the default.
- **Multiple links:** paste up to 50 video or playlist links into one preview. Overlapping video IDs are merged.
- **Saved playlists:** use **Download new** to collect additions and replace missing files. Each playlist remembers its format, quality, and destination.
- **Duplicate skipping:** recognize saved or queued videos by YouTube ID and media type, even when their title changes.
- **A useful queue:** see total speed, progress, approximate time remaining, and free disk space. Pause new starts, cancel individual items, or retry failures.
- **Simple setup:** choose your download folder on first launch. Dark mode is the default.
- **Engine updates:** check for official yt-dlp updates inside Settings, with SHA-256 verification before installation.

## Download for Windows

| Download | Who it is for |
| --- | --- |
| **[EXE only — Offbeat 1.3.1 for Windows x64](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/releases/download/v1.3.1-beta.1/Offbeat-1.3.1-Windows-x64.exe)** | **Recommended:** download, open, and use Offbeat. |
| [Source code ZIP](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/archive/refs/tags/v1.3.1-beta.1.zip) | Developers who want to inspect or modify the code. |
| [Checksums and license notices](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/releases/tag/v1.3.1-beta.1) | Optional verification and third-party license details. |

**No Python, terminal, or installer required.** Download the EXE to a writable folder and open it.

1. Choose where to save your music and videos.
2. On the first launch, wait while Offbeat downloads and verifies yt-dlp, Deno, and FFmpeg directly from their official releases. This needs internet access and may take a few minutes. Your tools are reused on later launches.
3. Paste links, choose **Music** or **Video**, and click **Download** after checking your selection.

Requires **64-bit Windows 10/11**, internet access, and the [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/). This beta EXE is unsigned, so Windows may show an unfamiliar-app warning. No instructions to disable security software are needed.

Offbeat creates **Offbeat-files/** beside the EXE for its tools and settings. Keep that folder when upgrading or moving the app. Media goes to your chosen download folder. If an older `data/library.json` already exists beside the EXE, Offbeat reuses that installation's data and tools instead.

[Release notes and checksums](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/releases/tag/v1.3.1-beta.1) · [Report a problem](https://github.com/RAFIK-404/Offbeat-YouTube-Music-Video-Downloader/issues/new/choose)

<details>
<summary>Run from source instead</summary>

Install Python 3.11+, download this repository, and run these commands in its folder:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

The app prepares missing download tools after you choose a folder. Developers can also run `scripts/fetch_tools.py` explicitly.

</details>

See the [user guide](docs/USAGE.md) for formats, duplicate rules, upgrades, and queue controls, or the [troubleshooting guide](docs/TROUBLESHOOTING.md) when something fails.

## What to expect from the beta

- Windows is the supported desktop platform. macOS and Linux desktop builds have not been validated.
- Availability depends on YouTube. Private, region-restricted, removed, sign-in-required, or bot-challenged items may not download. Offbeat does not import browser cookies or account credentials.
- Different uploads of the same song count as different videos. Duplicate detection does not use audio fingerprinting.
- Higher MP3 bitrate cannot restore quality missing from the source. More simultaneous downloads do not guarantee proportional speed increases.
- **Pause queue** lets active transfers finish. Closing the app interrupts active work; reopening holds unfinished work until you retry and resume.
- Time remaining is an estimate. **Calculating…** appears until sufficient transfer data is available.
- In-app updates cover **yt-dlp only**, not Offbeat, FFmpeg, or Deno.

Use Offbeat for content you own or have permission to save. Offbeat is an independent project and is not affiliated with YouTube or Google.

## Your data

For the standalone EXE, settings, saved playlists, and download history stay in `Offbeat-files/data/` beside the EXE. Source and older portable installations use `data/` in their app folder. Media goes to the folder you choose. The interface talks to a local server bound to `127.0.0.1`, with a different access token on each launch.

Offbeat's own code has no analytics or telemetry. It contacts YouTube for metadata and media, YouTube's image service for thumbnails, and GitHub for requested dependency downloads or update checks. Keep the `data/` folder private: it contains your playlist links, history, and local paths.

## Development

The backend uses Python's standard library. The desktop shell uses pywebview, and the interface is plain HTML, CSS, and JavaScript.

```powershell
# Run deterministic backend/API tests without downloading media
py -3 -m unittest discover -s tests -v

# Check frontend syntax (Node.js required for this check only)
node --check web/app.js

# Build the standalone EXE, after the source setup steps above
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe scripts\build_exe.py
```

The standalone EXE is written to `dist/`. It contains the app, Python, its desktop dependencies, and their license notices. Download tools are fetched on the end user's computer. See [release preparation](docs/RELEASING.md) for verification and packaging.

The current suite has **49 automated tests** covering queue behavior, persistence, duplicates, saved playlists, updates, first-run setup, API access checks, component verification, interrupted setup, and installation rollback. See [CONTRIBUTING.md](CONTRIBUTING.md) for development and issue-reporting guidelines. GitHub Actions runs the suite and JavaScript syntax check on Windows after pushes and pull requests.

## License and credits

Offbeat's original application code and interface are licensed under the [MIT License](LICENSE). Dependencies and bundled notices keep their own licenses; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

Built with [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org/), [Deno](https://deno.com/), and [pywebview](https://pywebview.flowrl.com/). The feature scope was inspired by [YoutubePlaylistDownloader](https://github.com/shaked6540/YoutubePlaylistDownloader); its code and assets were not copied.
