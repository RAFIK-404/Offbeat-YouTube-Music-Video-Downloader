# Contributing to Offbeat

Small, focused improvements are welcome. For a larger feature, open an issue describing the problem and proposed behavior before starting implementation.

## Set up

Use the source setup steps in [README.md](README.md). Windows is the supported desktop target. Runtime dependencies are pinned in `requirements.txt`; packaging dependencies are in `requirements-build.txt`.

For browser development, launch the same interface without a native window:

```powershell
.venv\Scripts\python.exe app.py --headless --data-dir work\dev-data
```

Open the printed local URL, including its fragment token. Browse for folders is available only in the native desktop app. Close the development server with Ctrl+C. Never share its token-bearing URL or expose its port to the network.

## Before submitting a change

Run these checks from the repository root:

```powershell
py -3 -m unittest discover -s tests -v
node --check web/app.js
```

The unit suite uses test subprocesses and mocked network responses; it does not require downloader binaries or YouTube access. Add a regression test when changing queue behavior, persistence, API input handling, or update installation. For interface changes, check the actual desktop view, keyboard controls, dark theme, and minimum window size.

Keep file operations within the selected destination. Preserve existing settings and history. A failed download must not become a successful duplicate record. Updates must verify the expected official artifact before replacing the installed engine.

## Report a problem

Use the bug-report template. Include the Offbeat version, Windows version, selected media format, a short error excerpt, and steps to reproduce. Share a YouTube URL only when you are comfortable making it public.

Remove usernames, local paths, private/unlisted links, cookies, tokens, and account information from screenshots and logs. Do not attach `data/library.json` or connection files. For sensitive reports, use GitHub's private vulnerability reporting if the repository owner has enabled it; do not publish exploit details or secrets in a public issue.

## Pull requests

Explain the user-visible problem, the change, and how you checked it. Do not commit binaries, downloaded media, user state, caches, or dependency archives. Include only changes related to the issue. Contributions to original Offbeat code are made under the repository's MIT License; retain third-party notices and compatible licensing for imported material.
