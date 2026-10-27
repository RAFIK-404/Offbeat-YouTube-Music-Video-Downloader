# Third-party components

Offbeat's original application code and interface are covered by the repository's [MIT License](LICENSE). That license does not apply to third-party software or the copied license texts in `third-party/`.

The public standalone EXE bundles the Python runtime and desktop-interface dependencies. It does **not** bundle yt-dlp, Deno, or FFmpeg: first-launch setup retrieves their official releases directly to the end user's computer, verifies the published SHA-256 digests, and records the downloaded versions and hashes in `Offbeat-files/bin/tools-manifest.json`. These projects remain separately licensed:

| Component | Upstream and licensing information |
| --- | --- |
| yt-dlp | [Source and license](https://github.com/yt-dlp/yt-dlp#license). Source is under the Unlicense; official executables bundle additional components with their own licenses. Preserve their third-party notices. |
| Deno | [Source](https://github.com/denoland/deno) and [license](https://github.com/denoland/deno/blob/main/LICENSE.md). MIT for Deno, with separately licensed dependencies. |
| FFmpeg / FFprobe | [Source and licensing](https://ffmpeg.org/legal.html). The selected Windows build from [yt-dlp/FFmpeg-Builds](https://github.com/yt-dlp/FFmpeg-Builds) includes GPL components. Offbeat invokes FFmpeg as a separate executable. |
| Microsoft WebView2 SDK | The WebView2 SDK loader and managed DLLs supplied with pywebview are included. The exact 1.0.3856.49 SDK license and notices are preserved in `third-party/` and embedded in the EXE. The WebView2 browser runtime itself is a system prerequisite. |
| Python | [PSF license](https://docs.python.org/3/license.html). |
| pywebview | [Source and BSD-3-Clause license](https://github.com/r0x0r/pywebview). |
| pythonnet | [Source and MIT license](https://github.com/pythonnet/pythonnet). |
| Other Python dependencies | clr-loader, CFFI, pycparser, bottle, proxy_tools, typing_extensions, and other installed distributions retain their own licenses. The build script collects installed license and notice files when supplied by those distributions. |
| PyInstaller bootloader | [GPL with distribution exception](https://pyinstaller.org/en/stable/license.html). |

The standalone build embeds the original Offbeat license, this notice, the Microsoft SDK notices, Python's license, and installed Python distribution licenses in `THIRD-PARTY-LICENSES.txt`. They can be opened from **Settings → Licenses** and are also attached to the release. Dependency tools downloaded later retain their upstream licenses and distribution terms.

The older development-only offline bundle produced by `scripts/build.py` includes FFmpeg and other tool binaries. It is not the public standalone distribution; redistributing it requires the matching corresponding-source and notice package. See [release preparation](docs/RELEASING.md).

The source repository contains no downloaded music, videos, browser cookies, or user library records. Video thumbnails are requested directly from YouTube when items are displayed.

The feature scope was inspired by [YoutubePlaylistDownloader](https://github.com/shaked6540/YoutubePlaylistDownloader). Its code and assets were not copied. Offbeat is not affiliated with YouTube, Google, or the upstream dependency projects.
