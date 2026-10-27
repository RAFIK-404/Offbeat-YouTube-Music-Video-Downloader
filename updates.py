"""User-initiated updates from the official yt-dlp release repository."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.request import Request, urlopen
import uuid

CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
VERSION = re.compile(r"^\d{4}\.\d{2}\.\d{2}(?:\.\d+)?$")


class DownloaderUpdater:
    def __init__(self, binary: Path):
        self.binary = binary

    def version(self, path=None):
        result = subprocess.run([str(path or self.binary), "--ignore-config", "--no-plugin-dirs", "--version"], capture_output=True, text=True, timeout=20, creationflags=CREATE_FLAGS)
        version = result.stdout.strip()
        if result.returncode or not VERSION.fullmatch(version):
            raise ValueError("Could not read the installed downloader version.")
        return version

    def check(self):
        current = self.version()
        request = Request("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest", headers={"User-Agent":"Offbeat", "Accept":"application/vnd.github+json"})
        with urlopen(request, timeout=30) as response:
            release = json.load(response)
        latest = release.get("tag_name", "")
        if not VERSION.fullmatch(latest) or release.get("prerelease") or release.get("draft"):
            raise ValueError("The official release information was not recognized. Try again later.")
        asset = next((a for a in release.get("assets", []) if a.get("name") == "yt-dlp.exe"), {})
        url = f"https://github.com/yt-dlp/yt-dlp/releases/download/{latest}/yt-dlp.exe"
        digest = asset.get("digest", "")
        if asset.get("browser_download_url") != url or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
            raise ValueError("This release has no verified Windows download. Your current version is unchanged.")
        available = tuple(map(int, latest.split('.'))) > tuple(map(int, current.split('.')))
        return {"current":current, "latest":latest, "available":available, "url":url, "sha256":digest[7:].lower()}

    def install(self, release, stopping, progress):
        # The manager supplies the checked release, never a client-provided URL or path.
        stage = self.binary.with_name("yt-dlp-update-" + uuid.uuid4().hex + ".exe")
        try:
            request = Request(release["url"], headers={"User-Agent":"Offbeat"})
            digest = hashlib.sha256()
            received = 0
            deadline = time.monotonic() + 180
            with urlopen(request, timeout=30) as response, stage.open("xb") as destination:
                total = int(response.headers.get("Content-Length") or 0)
                while True:
                    if stopping.is_set() or time.monotonic() > deadline:
                        raise ValueError("Update interrupted. The installed downloader is unchanged.")
                    block = response.read(256 * 1024)
                    if not block:
                        break
                    received += len(block)
                    if received > 150 * 1024 * 1024:
                        raise ValueError("Unexpected update size. The installed downloader is unchanged.")
                    digest.update(block)
                    destination.write(block)
                    progress(min(99, int(received / total * 100)) if total else 0)
            if digest.hexdigest() != release["sha256"]:
                raise ValueError("Update verification failed. The installed downloader is unchanged.")
            if self.version(stage) != release["latest"]:
                raise ValueError("Unexpected downloader version. The installed downloader is unchanged.")
            if stopping.is_set():
                raise ValueError("Update interrupted. The installed downloader is unchanged.")
            os.replace(stage, self.binary)
            return release["latest"]
        finally:
            stage.unlink(missing_ok=True)
