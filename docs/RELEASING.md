# Preparing a Windows release

## Standalone EXE

Build on 64-bit Windows using a dedicated Python environment:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe scripts\build_exe.py
```

The EXE bundles Python, pywebview, desktop dependencies, and their license notices. It does not bundle yt-dlp, Deno, FFmpeg, or FFprobe. First-launch setup downloads those tools directly from the official release repositories on the user's computer. No Python installation is needed on that computer. WebView2 remains a system prerequisite.

`Offbeat-files/` beside the EXE stores tools and app data. A pre-existing `data/library.json` beside the EXE selects the older portable layout, preserving settings and history. The `--app-dir` option supports isolated verification without touching a user's normal installation.

## Verify before uploading

1. Run `python -m unittest discover -s tests -v` and `node --check web/app.js`.
2. Start the built EXE with an empty app folder. Choose a destination and verify that official tool setup completes, manifests contain hashes, and all tools start.
3. Reopen the same profile and verify that setup does not repeat. Test a small audio/video download queue and duplicates.
4. Verify that the EXE contains runtime licenses and that `/licenses` returns them. Preserve Microsoft's WebView2 SDK license and notices alongside the Python licenses.
5. Confirm that release assets contain no local data, media, tokens, or personal paths. Compute SHA-256 checksums from the exact uploaded files.

For 1.3.1 use tag `v1.3.1-beta.1`, marked as a pre-release. Attach `Offbeat-1.3.1-Windows-x64.exe`, `THIRD-PARTY-LICENSES.txt`, and `SHA256SUMS.txt`. The tag must point to the tested source commit. GitHub also generates source archives. The EXE is unsigned; do not claim code signing or broad Windows compatibility testing that has not been performed.

## Earlier offline bundle

`scripts/build.py` remains available for local development with all tools bundled. Do not publish that older offline bundle without assembling its exact corresponding sources and notices. Its FFmpeg build includes GPL components, and the recorded moving `latest` tag does not identify a complete immutable source revision. The standalone release avoids redistributing those tool binaries; it retrieves them from their official publishers on each user's first launch.

References: [PyInstaller's distribution exception](https://pyinstaller.org/en/stable/license.html), [FFmpeg licensing](https://ffmpeg.org/legal.html), and [GitHub release assets](https://docs.github.com/en/rest/releases/assets).
