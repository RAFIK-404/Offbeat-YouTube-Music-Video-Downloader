# Offbeat user guide

A small Windows desktop app for YouTube music, videos, and full playlists.

## Use the portable app

1. Extract the entire **Offbeat-Windows-v1.3.zip** archive.
2. Open the **Offbeat** folder and double-click **Offbeat.exe**.
3. On first launch, choose your download folder using **Browse**, then click **Use this folder**.
4. Paste one or several YouTube links and click **Check links**.
5. Choose **Music (MP3)** or **Video (MP4)**, then choose quality.
6. Select the playlist items you want and click **Download**.

No Python installation, account, API key, or command prompt is needed. Windows 10/11, 64-bit, with Microsoft Edge WebView2 Runtime is required. WebView2 is already present on most Windows 10/11 computers. Keep the executable, `_internal`, and `bin` folders together. This is a portable, unsigned development build.

The **Full playlist** checkbox includes every listed item when a video link also contains a playlist ID. Uncheck it to take only the linked video. Incomplete playlist metadata is marked **Check on download** and stays selectable. Each download checks the video's actual availability; live/upcoming streams are excluded. A failed item does not stop the rest of a playlist.

The interface starts in **dark mode**. Downloads run **3 at once** by default. Change **Settings → Simultaneous downloads** to any number from 1 to 6. This applies to both MP3 and MP4, including playlists. Higher concurrency can improve throughput when a single transfer does not use the full connection; it does not guarantee a proportional speed increase. Reducing the limit lets current transfers finish before starting more.

## New in 1.3

**Multiple links:** Paste up to 50 video or playlist links, separated by spaces or new lines. Offbeat combines the results into one preview and merges matching video IDs across playlists. A failed link appears in a warning while successful results remain usable. The format and quality selected on this screen apply to the whole selection.

**Saved playlists:** Check a full playlist, choose format, quality, and destination, then click **Save playlist**. Find it in **Playlists** and click **Download new** to recheck YouTube and queue only new or missing files. Each saved playlist remembers its own settings. Duplicate skipping always applies to this action, including files already queued, even when the general duplicate setting is off. Refreshing never deletes local files when YouTube removes an item. Removing a saved playlist only removes the bookmark. To change its preferences, check the link again with the desired settings and save it again; music and video can have separate bookmarks. If the queue is paused, new items wait until you resume it.

**Downloader updates:** Open **Settings → Downloader updates → Check for updates**. If a newer official stable yt-dlp release is available, use **Install update**. Pause the queue and let active transfers and link checks finish first. New downloads wait during installation. Offbeat checks the official release's SHA-256 digest and executable version before replacing the engine. A failed verification leaves the installed version intact. This updates the **yt-dlp engine only**; Offbeat itself, FFmpeg, and Deno still use manual updates. Update checks happen only when requested.

**Download overview:** The queue shows combined transfer speed, saved/skipped totals, remaining items, progress, estimated time, and available disk space. Estimates use current transfers and recently completed files; **Calculating…** means there is not enough information yet. Connection delays and conversion can change estimates. A paused queue has no completion estimate. Totals cover the queue's current history until you clear finished rows. Free space includes destinations of unfinished jobs; when multiple destinations exist, the smallest available value is shown, with details on hover.

## Upgrade from 1.0, 1.1, or 1.2

Close the old Offbeat app first. Extract the new archive into the same parent folder as your existing `Offbeat` folder and allow the app files to be replaced. Keep the existing **data** and **Downloads** folders; neither is included in the update ZIP. Saved settings, history, duplicate detection, and queued items carry over. The new simultaneous-download setting defaults to 3. The queue stays paused after reopening if it contains unfinished work: use **Retry failed** for interrupted items, then **Resume queue**.

**Music:** MP3 at 128, 192, or 320 kbps. A higher export bitrate cannot improve the original source quality. **Video:** MP4 up to 720p, 1080p, 4K, or best available; the actual resolution depends on the source. MP4 may contain AV1 or another modern codec, depending on YouTube's formats and quality selection.

## Folders and duplicates

On first launch, Offbeat asks where to save downloads. It suggests `Downloads` beside the app; browse to another folder or confirm this suggestion. The folder is checked for write access before setup completes. Cancelling the folder picker or closing the app leaves setup pending for the next launch. After confirmation, Offbeat remembers your choice and opens normally. Existing installations keep their saved location without repeating setup. Use **Settings → Browse** to change it later. Music and Videos get separate subfolders. Settings, library records, and queue state live in `data` beside the executable.

Duplicate skipping is on by default. Offbeat matches the **YouTube video ID plus media type**, not the title. It checks saved files from earlier sessions, existing files with `[video-id]` in the selected folder's filenames, and items already queued. An MP3 does not block the MP4 of the same video. Changing the video resolution or MP3 bitrate still counts as the same media type; turn off skipping to save an additional version with a unique filename.

Files deleted from their recorded location can be downloaded again. Different uploads of the same song are separate video IDs; Offbeat does not perform audio fingerprinting or identify arbitrary files without IDs. Keeping the `data` folder preserves history. If you move the entire portable app, update the download location in Settings.

**Pause queue** lets active files finish and holds the rest of the queue. **Cancel** stops only the chosen download. **Retry** resumes its partial data when the source supports it. **Retry failed** requeues failed/interrupted items together. Closing the app stops all active items; the next launch holds unfinished work until you retry interrupted items and resume the queue. Clearing finished queue rows does not delete media or duplicate history.

Temporary connection errors and ambiguous availability errors get one automatic retry. Rate-limit responses pause new starts briefly. Error messages distinguish format, connection, sign-in, region, and explicit private/removal responses; “format not available” is no longer labeled private or removed. Browser playback can depend on an account, location, or a different upload, so an unavailable response alone does not establish the cause.

Use content you own or have permission to download. YouTube can change its delivery system or request sign-in; restricted or bot-challenged content may not download. Offbeat does not import browser cookies or credentials.

## Run from source

Use Python 3.11+ on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts\fetch_tools.py
.venv\Scripts\python app.py
```

`fetch_tools.py` downloads current official Windows yt-dlp, Deno, and FFmpeg builds, verifies their GitHub-provided SHA-256 digests, and writes `tools-manifest.json`. Close Offbeat before refreshing these tools. Prefer the in-app downloader update in Settings. The portable build also includes **Update downloader.cmd** for use while Offbeat is closed, and supports `bin\yt-dlp.exe -U`.

For browser development:

```powershell
python app.py --headless --data-dir work\dev-data --downloads C:\full\path\to\downloads
```

Open the printed URL including its fragment token. The server binds only to `127.0.0.1`; API calls require the per-launch token and an allowed Host/Origin. No cloud service is required. Folder browsing uses the native desktop bridge; type a path when testing in a normal browser.

## Build

```powershell
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python scripts\build.py
```

This creates `dist/Offbeat`. Keep its complete directory. The bundle includes the Python runtime, WebView2 bridge, download engine, JavaScript runtime, FFmpeg, and FFprobe. It uses the installed WebView2 runtime rather than bundling a second browser.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests cover URL normalization and source validation, playlist and queue duplicates, persistence, independent audio/video records, existing files, deleted files, automatic retries, concurrent workers, cancellation isolation, live concurrency limits, pause/close, settings migration, first-run folder setup, error classification, request authentication, and cross-origin rejection. Version 1.3 adds tests for combined previews, partial failures, saved-playlist refreshes and preferences, update verification and installation guards, and overview calculations. Fake subprocesses exercise deterministic queue behavior without contacting YouTube.

## Implementation

- `app.py`: local HTTP API, desktop window, folder picker, single-instance guard.
- `engine.py`: yt-dlp subprocesses, structured progress, queue, atomic JSON persistence.
- `updates.py`: explicit official-release checks and verified staged engine replacement.
- `overview.py`: transfer totals, time estimates, and destination disk space.
- `web/`: dependency-free HTML, CSS, and JavaScript interface.
- `scripts/`: verified dependency download and Windows packaging.
- `tests/`: backend and API tests.

The reference project inspired the scope; its code and assets were not copied. See `THIRD-PARTY-NOTICES.md` and `tools-manifest.json` for bundled components.
