"""Download official, SHA-256 verified Windows tools into bin/."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = [
    ("yt-dlp/yt-dlp", "yt-dlp.exe"),
    ("denoland/deno", "deno-x86_64-pc-windows-msvc.zip"),
    ("yt-dlp/FFmpeg-Builds", "ffmpeg-master-latest-win64-gpl-shared.zip"),
]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(spec):
    repo, name = spec
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"User-Agent": "Offbeat-build"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        release = json.load(response)
    asset = next(a for a in release["assets"] if a["name"] == name)
    digest = asset.get("digest", "")
    if not digest.startswith("sha256:"):
        raise RuntimeError(f"No SHA-256 digest supplied for {name}")
    cache = ROOT / "build-cache"
    cache.mkdir(exist_ok=True)
    target = cache / name
    if not target.exists() or sha256(target) != digest[7:]:
        print(f"Downloading {name}", flush=True)
        with urllib.request.urlopen(asset["browser_download_url"], timeout=120) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    if sha256(target) != digest[7:]:
        raise RuntimeError(f"Checksum mismatch: {name}")
    bindir = ROOT / "bin"
    bindir.mkdir(exist_ok=True)
    if name.endswith(".exe"):
        shutil.copy2(target, bindir / name)
    else:
        with zipfile.ZipFile(target) as archive:
            for entry in archive.infolist():
                basename = Path(entry.filename).name
                if basename in {"deno.exe", "ffmpeg.exe", "ffprobe.exe"} or ("/bin/" in entry.filename and basename.endswith(".dll")):
                    with archive.open(entry) as src, (bindir / basename).open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                elif basename.lower().startswith(("license", "copying")) and not entry.is_dir():
                    licenses = ROOT / "third-party"
                    licenses.mkdir(exist_ok=True)
                    with archive.open(entry) as src, (licenses / (repo.replace("/", "-") + "-" + basename)).open("wb") as dst:
                        shutil.copyfileobj(src, dst)
    print(f"Verified {repo} {release['tag_name']}", flush=True)
    license_files = {"yt-dlp/yt-dlp": ["LICENSE", "THIRD_PARTY_LICENSES.txt"], "denoland/deno": ["LICENSE.md"]}.get(repo, [])
    for filename in license_files:
        license_dir = ROOT / "third-party"
        license_dir.mkdir(exist_ok=True)
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{repo}/{release['tag_name']}/{filename}", timeout=60) as response:
            (license_dir / (repo.replace("/", "-") + "-" + filename)).write_bytes(response.read())
    return {"project": repo, "version": release["tag_name"], "url": asset["browser_download_url"], "sha256": digest[7:]}


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        manifest = list(pool.map(fetch, TOOLS))
    (ROOT / "tools-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
