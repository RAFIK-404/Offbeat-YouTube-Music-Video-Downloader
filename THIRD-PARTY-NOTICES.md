# Third-party components

Offbeat's original application code and interface are covered by the repository's [MIT License](LICENSE). That license does not apply to third-party software or the copied license texts in `third-party/`.

The source repository does not contain executable dependencies. Its setup script retrieves official releases directly to the user's computer. The local portable build contains separately licensed components:

| Component | Upstream and licensing information |
| --- | --- |
| yt-dlp | [Source and license](https://github.com/yt-dlp/yt-dlp#license). Source is under the Unlicense; official executables bundle additional components with their own licenses. Preserve their third-party notices. |
| Deno | [Source](https://github.com/denoland/deno) and [license](https://github.com/denoland/deno/blob/main/LICENSE.md). MIT for Deno, with separately licensed dependencies. |
| FFmpeg / FFprobe | [Source and licensing](https://ffmpeg.org/legal.html). The selected Windows build from [yt-dlp/FFmpeg-Builds](https://github.com/yt-dlp/FFmpeg-Builds) includes GPL components. Offbeat invokes FFmpeg as a separate executable. |
| Python | [PSF license](https://docs.python.org/3/license.html). |
| pywebview | [Source and BSD-3-Clause license](https://github.com/r0x0r/pywebview). |
| pythonnet | [Source and MIT license](https://github.com/pythonnet/pythonnet). |
| Other Python dependencies | clr-loader, CFFI, pycparser, bottle, proxy_tools, typing_extensions, and other installed distributions retain their own licenses. The build script collects installed license and notice files when supplied by those distributions. |
| PyInstaller bootloader | [GPL with distribution exception](https://pyinstaller.org/en/stable/license.html). |

The collected license texts are a starting inventory, not a statement that a binary release's redistribution requirements are complete. See [release preparation](docs/RELEASING.md) before distributing bundled executables. `tools-manifest.json` records versions, download URLs, and archive hashes for the local build; a moving release tag is not a complete source provenance record.

Microsoft Edge WebView2 is a system prerequisite and is not redistributed by Offbeat. The source repository does not contain downloaded music, videos, browser cookies, or user library records. Video thumbnails are requested directly from YouTube when items are displayed.

The feature scope was inspired by [YoutubePlaylistDownloader](https://github.com/shaked6540/YoutubePlaylistDownloader). Its code and assets were not copied. Offbeat is not affiliated with YouTube, Google, or the upstream dependency projects.
