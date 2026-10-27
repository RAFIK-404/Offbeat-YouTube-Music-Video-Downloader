# Troubleshooting

## A video plays on YouTube but fails here

Check the exact upload's video ID, rather than searching for the same song title. A browser session can have account access that the downloader does not have. Offbeat does not import browser cookies or support account sign-in.

Use **Settings → Downloader updates → Check for updates**, then retry the failed item. If the error mentions a missing format, try another quality. An ambiguous unavailable response is not proof that a video is private or removed. Some unavailable entries remain selectable so the actual download can check access.

## Downloads slow down or fail together

Reduce **Simultaneous downloads** to one or two and retry later. Offbeat retries certain transient errors once and briefly delays new starts after rate-limit responses. Increasing concurrency is not always faster.

## Nothing starts after reopening

Unfinished queues reopen paused. Use **Retry failed** for interrupted items, then **Resume queue**. Pausing normally lets active files finish.

## A saved playlist adds nothing

Download new skips matching video IDs that are already saved or queued for that media type. It uses the playlist's remembered destination and format, regardless of the current composer settings. Deleting a recorded file allows it to be queued again. Resave the playlist with new settings to update its preferences.

## A different upload of the same song downloads again

Duplicate checks use YouTube IDs and media type. Offbeat does not compare audio content or recognize arbitrary filenames without IDs. Audio and video versions are separate records.

## MP4 playback or audio quality looks different

An MP4 can contain a modern codec that your player does not support. Try another player or a lower quality. A 320 kbps MP3 export does not improve a lower-quality original recording.

## Folder selection or saving fails

Choose a folder you can write to, with sufficient free space. Keep the EXE in a writable folder. A fresh standalone app stores settings and history in `Offbeat-files/data/` beside it; older portable installations retain `data/`. If you move the app, check the destination in Settings; saved playlists also remember their own paths.

## The desktop window will not open

Confirm that you are using 64-bit Windows and have the Microsoft Edge WebView2 Runtime. Source users also need Python 3.11+ and the dependencies from `requirements.txt`. The standalone EXE prepares missing tools on first launch. Keep its `Offbeat-files/` folder when moving or upgrading it. Older folder-based builds still need their `_internal` and `bin` directories.

## An engine update fails

Pause the queue and wait for active transfers and link checks to finish. Check your internet connection and that the app's `bin/` folder is writable. Offbeat verifies the official digest and executable version before replacement. If verification fails, the existing engine remains installed. The update button does not update Offbeat, Deno, or FFmpeg.

## Reporting an issue

Include a minimal reproduction and the error text. Redact personal paths, tokens, and private playlist links. Never attach your entire `data/` folder. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## First-launch tool setup fails

Keep the internet connection on and check that GitHub downloads are reachable. Setup needs enough disk space for the tools and temporary archives. Use **Retry setup** after correcting the issue. A digest mismatch prevents installation; do not substitute an unverified executable. Closing during setup is safe for installed tools; reopen to start setup again.
