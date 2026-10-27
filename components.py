"""Fetch required tools directly from official releases on the user's computer."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen
import uuid
import zipfile

TOOLS = (
    ('yt-dlp', 'yt-dlp/yt-dlp', 'yt-dlp.exe', ('yt-dlp.exe',)),
    ('Deno', 'denoland/deno', 'deno-x86_64-pc-windows-msvc.zip', ('deno.exe',)),
    ('FFmpeg', 'yt-dlp/FFmpeg-Builds', 'ffmpeg-master-latest-win64-gpl-shared.zip', ('ffmpeg.exe', 'ffprobe.exe')),
)
REQUIRED = ('yt-dlp.exe', 'deno.exe', 'ffmpeg.exe', 'ffprobe.exe')
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


class ComponentInstaller:
    def __init__(self, bindir):
        self.bindir = Path(bindir)

    def release(self, repo, filename):
        request = Request(f'https://api.github.com/repos/{repo}/releases/latest', headers={'User-Agent':'Offbeat-setup', 'Accept':'application/vnd.github+json'})
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
        tag = data.get('tag_name', '')
        if data.get('draft') or data.get('prerelease') or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', tag):
            raise ValueError('The official release information could not be verified.')
        asset = next((a for a in data.get('assets', []) if a.get('name') == filename), {})
        url = f'https://github.com/{repo}/releases/download/{tag}/{filename}'
        digest = asset.get('digest', '')
        if asset.get('browser_download_url') != url or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
            raise ValueError('No verified official download was found. Please try again later.')
        return {'project':repo, 'version':tag, 'url':url, 'sha256':digest[7:].lower()}

    def download(self, release, target, stopping, progress):
        digest = hashlib.sha256()
        received = 0
        deadline = time.monotonic() + 900
        request = Request(release['url'], headers={'User-Agent':'Offbeat-setup'})
        with urlopen(request, timeout=30) as response, target.open('xb') as output:
            total = int(response.headers.get('Content-Length') or 0)
            while True:
                if stopping.is_set():
                    raise ValueError('Setup interrupted. Reopen Offbeat to try again.')
                if time.monotonic() > deadline:
                    raise ValueError('The download took too long. Check your connection and retry setup.')
                block = response.read(256 * 1024)
                if not block:
                    break
                received += len(block)
                if received > 400 * 1024 * 1024:
                    raise ValueError('Unexpected component size. Nothing was installed.')
                output.write(block)
                digest.update(block)
                progress(min(.99, received / total) if total else 0, received)
        if digest.hexdigest() != release['sha256']:
            raise ValueError('Download verification failed. Nothing was installed. Retry setup.')

    def unpack(self, archive_path, stage, required):
        seen = set()
        unpacked = 0
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                parts = PurePosixPath(entry.filename.replace('\\','/')).parts
                basename = parts[-1] if parts else ''
                if entry.is_dir() or not (basename in required or ('bin' in parts and basename.lower().endswith('.dll'))):
                    continue
                if basename in seen or entry.file_size < 1:
                    raise ValueError('Unexpected component archive contents.')
                seen.add(basename)
                unpacked += entry.file_size
                if unpacked > 1536 * 1024 * 1024 or len(seen) > 500:
                    raise ValueError('Unexpected expanded component size.')
                # Only known executable names and DLL basenames are written;
                # archive paths are never used as destination paths.
                with archive.open(entry) as src, (stage / basename).open('xb') as dst:
                    shutil.copyfileobj(src, dst)
        if not set(required).issubset(seen):
            raise ValueError('The component archive is incomplete. Nothing was installed.')

    def verify(self, stage):
        for filename in REQUIRED:
            arguments = ['--ignore-config','--no-plugin-dirs','--version'] if filename == 'yt-dlp.exe' else ['--version'] if filename == 'deno.exe' else ['-version']
            result = subprocess.run([str(stage / filename), *arguments], capture_output=True, timeout=30, creationflags=CREATE_FLAGS)
            if result.returncode or not result.stdout:
                raise ValueError(f'{filename} could not start. Check Windows compatibility and retry setup.')

    def install(self, stopping, progress):
        self.bindir.parent.mkdir(parents=True, exist_ok=True)
        manifest = []
        with tempfile.TemporaryDirectory(prefix='.offbeat-setup-', dir=self.bindir.parent) as temporary:
            temporary = Path(temporary)
            stage = temporary / 'bin'
            stage.mkdir()
            for index, (name, repo, filename, required) in enumerate(TOOLS):
                if stopping.is_set():
                    raise ValueError('Setup interrupted. Reopen Offbeat to try again.')
                progress(round(index / 3 * 90), f'Finding the official {name} release…')
                release = self.release(repo, filename)
                archive = temporary / filename
                self.download(release, archive, stopping, lambda fraction, received: progress(round((index + fraction) / 3 * 90), f'Downloading {name} · {received / 1048576:.1f} MB'))
                progress(round((index + 1) / 3 * 90), f'Verifying {name}…')
                if filename.endswith('.exe'):
                    shutil.copy2(archive, stage / filename)
                else:
                    self.unpack(archive, stage, required)
                manifest.append(release)
            if stopping.is_set():
                raise ValueError('Setup interrupted. Reopen Offbeat to try again.')
            progress(95, 'Checking the download tools…')
            self.verify(stage)
            (stage / 'tools-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            if stopping.is_set():
                raise ValueError('Setup interrupted. Reopen Offbeat to try again.')
            backup = self.bindir.with_name('.offbeat-tools-backup-' + uuid.uuid4().hex)
            had_previous = self.bindir.exists()
            if had_previous:
                os.replace(self.bindir, backup)
            try:
                os.replace(stage, self.bindir)
            except OSError:
                if had_previous:
                    os.replace(backup, self.bindir)
                raise
            if had_previous:
                # Keep a backup if Windows temporarily holds a file open.
                try:
                    shutil.rmtree(backup)
                except OSError:
                    pass
        progress(100, 'Ready to download. Your tools are installed.')
        return manifest
