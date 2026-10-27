# Preparing a release

## Initial publication

The prepared GitHub package contains application source, documentation, tests, and a screenshot of an empty app. It excludes executable dependencies, user history, downloaded media, and local verification artifacts.

Publish the first version as a **pre-release**, with tag `v1.3.0-beta.1` and title **Offbeat 1.3 — First public beta**. The application displays version 1.3. The suffix identifies the initial public distribution of that version.

Before publication, the owner should review the prepared MIT license for original Offbeat code. This license does not replace dependency licenses. Run the test workflow once the repository exists; local tests do not establish that a hosted Actions run has passed.

## Validation

```powershell
py -3 -m unittest discover -s tests -v
node --check web/app.js
```

For a new Windows build, test fresh startup, folder selection, reopening with existing settings, a small parallel-download queue, duplicates, and an engine update check using an isolated profile. Confirm that shutdown leaves recoverable work and that the next launch does not silently start unfinished transfers.

## Bundled Windows release: remaining work

The existing local portable ZIP is **not cleared for public redistribution**. Its FFmpeg package is a GPL build, and the collected license text and upstream links do not establish that a complete corresponding-source distribution has been supplied. The recorded FFmpeg URL uses a moving `latest` tag, so it does not identify an immutable source revision by itself.

Before attaching a portable ZIP:

1. Identify the exact FFmpeg and linked-library revisions, build configuration, scripts, and patches corresponding to the distributed binaries. Retain the original verified archive and its hash.
2. Assemble the required corresponding sources and notices, and provide them with the binary release using the applicable distribution terms. Review the upstream executables' other bundled components as well, including yt-dlp, Deno, and the packaged Python runtime.
3. Preserve third-party notices in the app and release assets. Do not describe the entire bundle as MIT-licensed.
4. Build from the intended source revision, verify it on a clean Windows profile, and calculate SHA-256 hashes for the final archives.
5. Put ZIPs and source archives in **GitHub Releases**, not in the source repository. Keep `data/`, `Downloads/`, `.offbeat-partials/`, logs, and connection files out of every release archive.

Official references: [FFmpeg licensing information](https://ffmpeg.org/legal.html), [FFmpeg build project](https://github.com/yt-dlp/FFmpeg-Builds), [yt-dlp license information](https://github.com/yt-dlp/yt-dlp#license), and [GitHub binary distribution guidance](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github#distributing-large-binaries).

`tools-manifest.json` records the dependency archives used for the local 1.3 build. `scripts/fetch_tools.py` intentionally downloads the currently published releases and rewrites that manifest. It does not reproduce the recorded build exactly. The in-app yt-dlp update can also change the installed engine independently of the recorded build manifest.

Code signing and additional Windows 10/11 testing are recommended before calling the portable build stable. Existing local validation was performed on Windows 11, and packaged builds are unsigned.
