"""Package Offbeat for Windows. Run after fetch_tools.py."""
from importlib import metadata
from pathlib import Path
import argparse
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--work", type=Path, default=ROOT / "build")
    parser.add_argument("--tools", type=Path, default=ROOT / "bin")
    args = parser.parse_args()
    args.dist = args.dist.resolve()
    args.work = args.work.resolve()
    args.work.mkdir(parents=True, exist_ok=True)
    for name in ["yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"]:
        if not (args.tools / name).is_file():
            raise SystemExit("Missing tools. Run scripts/fetch_tools.py first.")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "Offbeat", "--distpath", str(args.dist), "--workpath", str(args.work), "--specpath", str(args.work), "--add-data", str(ROOT / "web") + ";web", "--collect-all", "webview", "--exclude-module", "PyQt5", "--exclude-module", "PyQt6", "--exclude-module", "PySide2", "--exclude-module", "PySide6", str(ROOT / "app.py")]
    if (ROOT / "web" / "app.ico").exists():
        command[3:3] = ["--icon", str(ROOT / "web" / "app.ico")]
    subprocess.run(command, check=True)
    target = args.dist / "Offbeat"
    shutil.copytree(args.tools, target / "bin", dirs_exist_ok=True)
    shutil.copytree(ROOT / "third-party", target / "third-party", dirs_exist_ok=True)
    shutil.copytree(ROOT / "docs", target / "docs", dirs_exist_ok=True)
    for name in ["README.md", "LICENSE", "CONTRIBUTING.md", "THIRD-PARTY-NOTICES.md", "tools-manifest.json", "Update downloader.cmd"]:
        shutil.copy2(ROOT / name, target / name)
    licenses = target / "third-party" / "python"
    licenses.mkdir(parents=True, exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    for distribution in metadata.distributions():
        for file in distribution.files or []:
            if file.name.lower().startswith(("license", "copying", "notice")) and ".dist-info/" in str(file).replace("\\", "/"):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    shutil.copy2(source, licenses / (distribution.metadata["Name"] + "-" + file.name))
    print("Portable app:", target / "Offbeat.exe")


if __name__ == "__main__":
    main()
