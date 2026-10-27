"""Download queue, durable library, and yt-dlp subprocess integration."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlparse
import uuid

from overview import queue_overview
from updates import DownloaderUpdater
from components import ComponentInstaller

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ACTIVE = {"queued", "downloading", "converting", "retrying"}
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def normalize_url(value: str, whole_playlist: bool = True) -> str:
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"} or parsed.username or parsed.password or parsed.port:
        raise ValueError("Paste a YouTube video or playlist link.")
    query = parse_qs(parsed.query)
    playlist = query.get("list", [""])[0]
    if playlist and whole_playlist:
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,150}", playlist):
            raise ValueError("This playlist link is not valid.")
        return "https://www.youtube.com/playlist?list=" + playlist
    video = query.get("v", [""])[0]
    parts = parsed.path.strip("/").split("/")
    if host.endswith("youtu.be"):
        video = parts[0]
    elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
        video = parts[1]
    if not VIDEO_ID.fullmatch(video):
        raise ValueError("Paste a link to a specific YouTube video or playlist.")
    return "https://www.youtube.com/watch?v=" + video


def stop_process(process):
    if process and process.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, creationflags=CREATE_FLAGS)
        else:
            process.terminate()


def classify_error(raw):
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    errors = [line for line in lines if "ERROR:" in line]
    message = (errors[-1] if errors else lines[-1] if lines else "The download did not finish. Try again.")
    message = re.sub(r"\x1b\[[0-9;]*m", "", message)[:800]
    lower = message.lower()
    code, delay, hint = "download", 0, ""
    if "requested format" in lower or "no video formats" in lower:
        code, hint = "format", "YouTube did not provide a matching media format. Try another quality."
    elif "private video" in lower:
        code, hint = "private", "YouTube says this video is private. Access requires an authorized account."
    elif any(s in lower for s in ("has been removed", "account has been terminated", "video has been deleted", "copyright claim", "copyright request")):
        code, hint = "removed", "YouTube reports that this upload was removed."
    elif any(s in lower for s in ("not available in your country", "not made this video available in your country", "geo restricted")):
        code, hint = "region", "YouTube restricts this video in your current region."
    elif "429" in lower or "too many requests" in lower or "content isn't available, try again later" in lower:
        code, delay, hint = "rate_limit", 30, "YouTube is limiting requests. Waiting before retrying; fewer simultaneous downloads may help."
    elif any(s in lower for s in ("sign in", "not a bot", "login required", "members-only", "join this channel")):
        code, hint = "sign_in", "YouTube requires sign-in or account access for this request."
    elif any(s in lower for s in ("timed out", "timeout", "connection", "network", "http error 5", "unable to download", "fragment")):
        code, delay, hint = "network", 3, "A connection or transfer error interrupted this download."
    elif "video unavailable" in lower or "video is not available" in lower or "video is unavailable" in lower:
        code, delay, hint = "unavailable", 3, "YouTube did not provide this video to the downloader. This does not confirm that it is private or removed."
    return {"code": code, "delay": delay, "message": (hint + " " + message).strip()}


def friendly_error(raw):
    return classify_error(raw)["message"]


class Engine:
    def __init__(self, root: Path):
        self.bin = root / "bin"

    def health(self):
        names = ["yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"]
        missing = [name for name in names if not (self.bin / name).is_file()]
        return {"ready": not missing, "missing": missing}

    def base_command(self):
        if not self.health()["ready"]:
            raise ValueError("Download components are missing. Run scripts/fetch_tools.py or use the full portable app.")
        return [str(self.bin / "yt-dlp.exe"), "--ignore-config", "--no-plugin-dirs", "--encoding", "utf-8", "--no-colors", "--socket-timeout", "20", "--retries", "3", "--extractor-retries", "2", "--js-runtimes", "deno:" + str(self.bin / "deno.exe"), "--ffmpeg-location", str(self.bin)]

    def preview(self, url):
        try:
            result = subprocess.run(self.base_command() + ["--flat-playlist", "--dump-single-json", "--ignore-errors", "--yes-playlist", "--", url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, creationflags=CREATE_FLAGS)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("YouTube took too long to respond. Check your connection and try the link again.") from exc
        if not result.stdout.strip():
            raise ValueError(friendly_error(result.stderr))
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(friendly_error(result.stderr)) from exc
        if not isinstance(data, dict):
            raise ValueError(friendly_error(result.stderr))
        entries = data.get("entries") if data.get("_type") in {"playlist", "multi_video"} else [data]
        items = []
        unavailable = 0
        for entry in entries or []:
            if not entry or not VIDEO_ID.fullmatch(entry.get("id", "")):
                unavailable += 1
                continue
            # Flat playlist metadata is only a hint. Let the actual extraction decide access.
            blocked = entry.get("live_status") in {"is_live", "is_upcoming"}
            uncertain = not entry.get("title") or entry.get("availability") in {"private", "premium_only", "subscriber_only", "needs_auth"} or entry.get("title") in {"[Private video]", "[Deleted video]"}
            note = "Live / upcoming" if blocked else "Check on download" if uncertain else ""
            items.append({"video_id": entry["id"], "title": entry.get("title") or "YouTube video · " + entry["id"], "channel": entry.get("channel") or entry.get("uploader") or "YouTube", "duration": entry.get("duration"), "unavailable": blocked, "availability_note": note})
        if not items:
            raise ValueError("No available videos were found in this link.")
        return {"title": data.get("title") or items[0]["title"], "items": items, "unavailable": unavailable, "is_playlist": len(items) > 1 or data.get("_type") == "playlist"}

    def download_command(self, job):
        folder = Path(job["folder"]) / ("Music" if job["mode"] == "audio" else "Videos")
        staging = Path(job["folder"]) / ".offbeat-partials" / job["id"]
        folder.mkdir(parents=True, exist_ok=True)
        staging.mkdir(parents=True, exist_ok=True)
        # Stable IDs avoid collisions. Explicit repeat downloads get a unique suffix.
        suffix = "" if job["skip_duplicates"] else " (" + job["id"][:8] + ")"
        template = "%(title).120B [%(id)s]" + suffix + ".%(ext)s"
        args = self.base_command() + ["--no-playlist", "--no-simulate", "--newline", "--progress", "--progress-delta", "0.4", "--windows-filenames", "--continue", "--no-overwrites", "--abort-on-unavailable-fragments", "--embed-metadata", "--paths", "home:" + str(folder), "--paths", "temp:" + str(staging), "--output", template, "--progress-template", "download:OFFBEAT_PROGRESS %(progress)j", "--progress-template", "postprocess:OFFBEAT_PROCESS %(progress.status)s", "--print", "after_move:OFFBEAT_FILE %(filepath)j"]
        if job["mode"] == "audio":
            args += ["--format", "bestaudio/best", "--extract-audio", "--audio-format", "mp3", "--audio-quality", job["quality"] + "K"]
        else:
            height = "" if job["quality"] == "best" else "[height<=" + job["quality"] + "]"
            args += ["--format", f"bv*{height}[ext=mp4]+ba[ext=m4a]/b{height}[ext=mp4]/bv*{height}+ba/b{height}", "--merge-output-format", "mp4", "--remux-video", "mp4"]
        return args + ["--print", "before_dl:OFFBEAT_TITLE %(title)j", "--", "https://www.youtube.com/watch?v=" + job["video_id"]]


class DownloadManager:
    def __init__(self, data_dir: Path, engine: Engine, default_folder: Path):
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "library.json"
        self.engine = engine
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.processes = {}
        self.workers = {}
        self.cancel_events = {}
        self.cooldown_until = 0
        self.thread = None
        self.preview_state = {"status": "idle"}
        self.update_state = {"status":"idle", "message":"Check for downloader updates when you need them.", "progress":0}
        self.update_release = None
        self.update_thread = None
        self.updater = DownloaderUpdater(engine.bin / "yt-dlp.exe") if hasattr(engine, "bin") else None
        self.component_installer = ComponentInstaller(engine.bin) if hasattr(engine, "bin") else None
        self.component_state = {"status":"idle", "progress":0, "message":"Preparing your download tools…"}
        self.component_thread = None
        self.state = {"settings": {"folder": str(default_folder), "mode": "audio", "audio_quality": "320", "video_quality": "1080", "skip_duplicates": True, "concurrent_downloads": 3}, "jobs": [], "library": [], "playlists": [], "paused": False, "setup_complete": False}
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                # Older installations already have a destination. Preserve their choice.
                saved.setdefault("setup_complete", bool(saved.get("settings", {}).get("folder")))
                saved["settings"] = {**self.state["settings"], **saved.get("settings", {})}
                self.state.update(saved)
            except (ValueError, OSError):
                # Preserve the bad file for recovery rather than overwriting it.
                self.path.rename(data_dir / ("library-recovery-" + str(int(time.time())) + ".json"))
        for job in self.state["jobs"]:
            if job["status"] in {"downloading", "converting", "retrying"}:
                job.update(status="interrupted", detail="App closed. Retry to continue the partial download.")
        for playlist in self.state["playlists"]:
            if playlist.get("sync_status") == "loading":
                playlist.update(sync_status="idle", message="Refresh interrupted. Download new to check again.")
        if any(job["status"] in ACTIVE or job["status"] == "interrupted" for job in self.state["jobs"]):
            self.state["paused"] = True
        self.save()

    def save(self):
        with self.lock:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.state)
            result["preview"] = copy.deepcopy(self.preview_state)
            result["health"] = self.engine.health()
            result["updater"] = copy.deepcopy(self.update_state)
            result["components"] = copy.deepcopy(self.component_state)
            result["cooldown_seconds"] = max(0, int(self.cooldown_until - time.monotonic()))
            for item in result["library"]:
                item["exists"] = Path(item["path"]).is_file()
        result["overview"] = queue_overview(result)
        if result["cooldown_seconds"] or result["updater"]["status"] == "installing":
            result["overview"]["eta_seconds"] = None
        return result

    def settings(self, changes):
        with self.lock:
            current = dict(self.state["settings"])
            for key in current:
                if key in changes:
                    current[key] = changes[key]
            if current["mode"] not in {"audio", "video"} or current["audio_quality"] not in {"128", "192", "320"} or current["video_quality"] not in {"720", "1080", "2160", "best"} or not isinstance(current["skip_duplicates"], bool):
                raise ValueError("Choose a valid format and quality.")
            if not isinstance(current["folder"], str) or not current["folder"].strip():
                raise ValueError("Choose a download folder.")
            if type(current["concurrent_downloads"]) is not int or not 1 <= current["concurrent_downloads"] <= 6:
                raise ValueError("Choose between 1 and 6 simultaneous downloads.")
            folder = Path(current["folder"]).expanduser()
            if not folder.is_absolute():
                raise ValueError("Enter a full folder path, such as C:\\Users\\you\\Downloads\\Offbeat.")
            current["folder"] = str(folder.resolve())
            if "folder" in changes:
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                    probe = folder / (".offbeat-write-test-" + uuid.uuid4().hex)
                    probe.write_bytes(b"")
                    probe.unlink()
                except OSError as exc:
                    raise ValueError("This folder is not writable. Choose another folder.") from exc
            self.state["settings"] = current
            if "folder" in changes:
                self.state["setup_complete"] = True
            self.save()
            self.wake.set()
            return current

    def existing(self, video_id, mode, folder):
        for item in reversed(self.state["library"]):
            if item["video_id"] == video_id and item["mode"] == mode and Path(item["path"]).is_file() and Path(item["path"]).stat().st_size > 0:
                return item["path"]
        extension = ".mp3" if mode == "audio" else ".mp4"
        for directory in [Path(folder), Path(folder) / ("Music" if mode == "audio" else "Videos")]:
            if directory.is_dir():
                for path in directory.glob("*" + extension):
                    if "[" + video_id + "]" in path.name and path.is_file() and path.stat().st_size > 0:
                        return str(path)
        return None

    def preview(self, url, whole_playlist=True, saved_playlist=None):
        if not self.engine.health()["ready"]:
            raise ValueError("Your download tools are being set up. Please wait for setup to finish.")
        tokens = url.split()
        if not tokens or len(tokens) > 50 or len(url) > 50000:
            raise ValueError("Paste between 1 and 50 YouTube links, separated by spaces or new lines.")
        urls, errors = [], []
        for token in tokens:
            try:
                normalized = normalize_url(token, whole_playlist)
                if normalized not in urls:
                    urls.append(normalized)
            except ValueError as exc:
                errors.append({"url":token[:200], "error":str(exc)})
        if not urls:
            raise ValueError("No valid YouTube links were found. " + errors[0]["error"])
        with self.lock:
            if self.update_state["status"] == "installing":
                raise ValueError("The downloader is updating. Try again when it finishes.")
            if self.preview_state["status"] == "loading":
                raise ValueError("Links are already being checked. Please wait.")
            preview_id = uuid.uuid4().hex
            self.preview_state = {"status":"loading", "id":preview_id, "url":urls[0], "checked":0, "link_count":len(urls)}
            if saved_playlist:
                saved_playlist.update(sync_status="loading", message="Checking for new or missing files…")
                self.save()

        def load():
            items, sources, seen = [], [], set()
            unavailable = duplicates = 0
            try:
                for index, source_url in enumerate(urls):
                    if self.stopping.is_set():
                        return
                    try:
                        result = self.engine.preview(source_url)
                        sources.append({"url":source_url, "title":result["title"], "is_playlist":result["is_playlist"], "item_count":len(result["items"])})
                        unavailable += result.get("unavailable", 0)
                        for item in result["items"]:
                            if item["video_id"] in seen:
                                duplicates += 1
                                continue
                            seen.add(item["video_id"])
                            items.append({**item, "playlist":result["title"]})
                    except Exception as exc:
                        errors.append({"url":source_url, "error":str(exc)[:800]})
                    with self.lock:
                        self.preview_state["checked"] = index + 1
                if not items:
                    raise ValueError(errors[0]["error"] if errors else "No videos were found in these links.")
                with self.lock:
                    title = sources[0]["title"] if len(sources) == 1 else f"{len(sources)} links · one collection"
                    self.preview_state.update(status="ready", title=title, items=items, sources=sources, errors=errors, duplicates=duplicates, unavailable=unavailable, is_playlist=any(source["is_playlist"] for source in sources))
                    if saved_playlist:
                        settings = {**self.state["settings"], "mode":saved_playlist["mode"], "folder":saved_playlist["folder"], saved_playlist["mode"] + "_quality":saved_playlist["quality"]}
                        result = self._add_entries([i for i in items if not i["unavailable"]], settings, title, only_new=True)
                        saved_playlist.update(title=title, item_count=len(items), last_checked=time.time(), sync_status="done", last_result=result, message=f"{result['added']} added · {result['skipped']} already saved or queued")
                        self.save()
            except Exception as exc:
                with self.lock:
                    self.preview_state.update(status="error", error=str(exc), errors=errors)
                    if saved_playlist:
                        saved_playlist.update(sync_status="error", message=str(exc)[:800])
                        self.save()
        threading.Thread(target=load, daemon=True).start()
        return {"id":preview_id}

    def save_playlists(self, preview_id):
        with self.lock:
            preview = self.preview_state
            if preview.get("id") != preview_id or preview["status"] != "ready":
                raise ValueError("Check the links before saving playlists.")
            settings = self.state["settings"]
            if not self.state["setup_complete"]:
                raise ValueError("Choose a download folder first.")
            sources = [source for source in preview.get("sources", []) if source["is_playlist"] and "/playlist?list=" in source["url"]]
            if not sources:
                raise ValueError("This preview does not contain a full playlist.")
            for source in sources:
                playlist = next((p for p in self.state["playlists"] if p["url"] == source["url"] and p["mode"] == settings["mode"]), None)
                if playlist is None:
                    playlist = {"id":uuid.uuid4().hex, "created":time.time()}
                    self.state["playlists"].append(playlist)
                playlist.update(url=source["url"], title=source["title"], item_count=source["item_count"], mode=settings["mode"], quality=settings[settings["mode"] + "_quality"], folder=settings["folder"], last_checked=time.time(), sync_status="idle", message="Ready to check for new or missing files.")
            self.save()
            return {"saved":len(sources)}

    def playlist_action(self, action, playlist_id):
        with self.lock:
            playlist = next((p for p in self.state["playlists"] if p["id"] == playlist_id), None)
            if not playlist:
                raise ValueError("This saved playlist no longer exists.")
            if playlist.get("sync_status") == "loading":
                raise ValueError("This playlist is being refreshed. Please wait.")
            if action == "remove":
                self.state["playlists"].remove(playlist)
                self.save()
                return {"removed":True}
            if action == "download_new":
                if not self.state["setup_complete"]:
                    raise ValueError("Choose a download folder first.")
                return self.preview(playlist["url"], True, saved_playlist=playlist)
            raise ValueError("Unknown playlist action.")

    def update_downloader(self, action):
        with self.lock:
            if self.component_state["status"] == "installing" or not self.engine.health()["ready"]:
                raise ValueError("Finish setting up the download tools first.")
            if action not in {"check", "install"}:
                raise ValueError("Unknown update action.")
            if self.update_state["status"] in {"checking", "installing"}:
                raise ValueError("An update operation is already running.")
            if self.updater is None:
                raise ValueError("Downloader updates are not available in this build.")
            if action == "install":
                if not self.update_release or not self.update_release["available"]:
                    raise ValueError("Check for an available update first.")
                if self.workers or self.processes or self.preview_state["status"] == "loading":
                    raise ValueError("Pause the queue and wait for active downloads and link checks to finish before updating.")
            self.update_state.update(status="checking" if action == "check" else "installing", message="Checking the official release…" if action == "check" else "Downloading and verifying the update…", progress=0)

        def progress(percent):
            with self.lock:
                self.update_state["progress"] = percent

        def run_update():
            try:
                if action == "check":
                    release = self.updater.check()
                    with self.lock:
                        self.update_release = release
                        self.update_state.update(status="available" if release["available"] else "current", current=release["current"], latest=release["latest"], message="A downloader update is available." if release["available"] else "Your downloader is up to date.")
                else:
                    version = self.updater.install(self.update_release, self.stopping, progress)
                    with self.lock:
                        self.update_release["available"] = False
                        self.update_state.update(status="current", current=version, latest=version, message="Downloader updated successfully. Ready to download.", progress=100)
            except Exception as exc:
                with self.lock:
                    self.update_release = None
                    self.update_state.update(status="error", message="Update failed. " + str(exc)[:600])
            finally:
                self.wake.set()
        self.update_thread = threading.Thread(target=run_update, daemon=True)
        self.update_thread.start()
        return {"ok":True}

    def setup_components(self):
        with self.lock:
            if self.engine.health()["ready"] or self.component_state["status"] == "installing":
                return {"ok":True}
            if self.component_installer is None:
                raise ValueError("Automatic setup is not available in this build.")
            if self.workers or self.processes or self.preview_state["status"] == "loading" or self.update_state["status"] in {"checking","installing"}:
                raise ValueError("Wait for active work to finish before setting up tools.")
            self.component_state.update(status="installing", progress=0, message="Connecting to the official download servers…")

        def progress(percent, message):
            with self.lock:
                self.component_state.update(progress=percent, message=message)

        def install():
            try:
                self.component_installer.install(self.stopping, progress)
                with self.lock:
                    self.component_state.update(status="ready", progress=100, message="Ready to download.")
            except Exception as exc:
                with self.lock:
                    self.component_state.update(status="error", message="Setup could not finish. " + str(exc)[:500])
            finally:
                self.wake.set()
        self.component_thread = threading.Thread(target=install, daemon=True)
        self.component_thread.start()
        return {"ok":True}

    def add(self, preview_id, video_ids):
        with self.lock:
            if not self.state["setup_complete"]:
                raise ValueError("Choose where to save your downloads first.")
            preview = self.preview_state
            if preview.get("id") != preview_id or preview["status"] != "ready":
                raise ValueError("Check the link again before adding downloads.")
            if not isinstance(video_ids, list) or not video_ids or not all(isinstance(v, str) for v in video_ids):
                raise ValueError("Select at least one video.")
            selected = set(video_ids)
            entries = [entry for entry in preview["items"] if entry["video_id"] in selected and not entry["unavailable"]]
            if not entries:
                raise ValueError("No available videos are selected.")
            return self._add_entries(entries, self.state["settings"], preview["title"])

    def _add_entries(self, entries, settings, playlist_title, only_new=False):
        folder = Path(settings["folder"])
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / (".offbeat-write-test-" + uuid.uuid4().hex)
        try:
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise ValueError("This folder is not writable. Choose another folder in Settings.") from exc
        added = skipped = 0
        settings = {**settings, "skip_duplicates": True} if only_new else settings
        mode = settings["mode"]
        known_files = {}
        if settings["skip_duplicates"]:
            for record in self.state["library"]:
                path = Path(record["path"])
                if record["mode"] == mode and path.is_file() and path.stat().st_size > 0:
                    known_files[record["video_id"]] = str(path)
            extension = ".mp3" if mode == "audio" else ".mp4"
            for directory in [folder, folder / ("Music" if mode == "audio" else "Videos")]:
                if directory.is_dir():
                    for path in directory.glob("*" + extension):
                        match = re.search(r"\[([A-Za-z0-9_-]{11})\]", path.name)
                        if match and path.is_file() and path.stat().st_size > 0:
                            known_files[match[1]] = str(path)
        pending_ids = {j["video_id"] for j in self.state["jobs"] if j["mode"] == mode and j["status"] in ACTIVE}
        for entry in entries:
            existing = known_files.get(entry["video_id"])
            pending = entry["video_id"] in pending_ids
            duplicate = settings["skip_duplicates"] and (existing or pending)
            if duplicate and only_new:
                skipped += 1
                continue
            job = {**entry, "id": uuid.uuid4().hex, "mode": mode, "quality": settings[mode + "_quality"], "folder": str(folder), "skip_duplicates": settings["skip_duplicates"], "status": "skipped" if duplicate else "queued", "progress": 0, "detail": "Already saved" if existing else "Already in the queue" if duplicate else "Waiting to download", "created": time.time(), "path": existing or "", "playlist": entry.get("playlist") or playlist_title}
            self.state["jobs"].append(job)
            if not duplicate:
                pending_ids.add(entry["video_id"])
            skipped += bool(duplicate)
            added += not bool(duplicate)
        self.save()
        self.wake.set()
        return {"added": added, "skipped": skipped}

    def action(self, action, job_id=None):
        process = None
        with self.lock:
            if action == "pause":
                self.state["paused"] = True
            elif action == "resume":
                self.state["paused"] = False
            elif action == "clear":
                self.state["jobs"] = [j for j in self.state["jobs"] if j["status"] in ACTIVE or j["status"] in {"error", "interrupted"} or j["id"] in self.workers]
            elif action == "retry_failed":
                for job in self.state["jobs"]:
                    if job["status"] in {"error", "interrupted"} and job["id"] not in self.workers:
                        job.update(status="queued", detail="Waiting to retry", progress=0)
            elif action in {"cancel", "retry"}:
                job = next((j for j in self.state["jobs"] if j["id"] == job_id), None)
                if not job:
                    raise ValueError("This download no longer exists.")
                if action == "retry":
                    if job_id in self.workers or job_id in self.processes:
                        raise ValueError("The previous download is stopping. Retry in a moment.")
                    if job["status"] not in {"error", "cancelled", "interrupted"}:
                        raise ValueError("Only failed or cancelled downloads can be retried.")
                    job.update(status="queued", detail="Waiting to retry", progress=0)
                elif job["status"] in ACTIVE:
                    job.update(status="cancelled", detail="Cancelled. You can retry anytime.")
                    if job_id in self.cancel_events:
                        self.cancel_events[job_id].set()
                    process = self.processes.get(job_id)
            else:
                raise ValueError("Unknown queue action.")
            self.save()
            self.wake.set()
        # A slow process-tree shutdown must not block other workers' progress.
        stop_process(process)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stopping.is_set():
            with self.lock:
                if self.component_state["status"] != "installing" and self.engine.health()["ready"] and self.update_state["status"] != "installing" and self.state["setup_complete"] and not self.state["paused"] and time.monotonic() >= self.cooldown_until and not self.stopping.is_set():
                    busy = {(j["video_id"], j["mode"]) for j in self.state["jobs"] if j["id"] in self.workers}
                    for job in self.state["jobs"]:
                        if len(self.workers) >= self.state["settings"]["concurrent_downloads"]:
                            break
                        key = (job["video_id"], job["mode"])
                        if job["status"] != "queued" or key in busy:
                            continue
                        job.update(status="downloading", detail="Connecting to YouTube…", attempt=1)
                        self.cancel_events[job["id"]] = threading.Event()
                        worker = threading.Thread(target=self.download, args=(job,), daemon=True)
                        self.workers[job["id"]] = worker
                        busy.add(key)
                        self.save()
                        worker.start()
            self.wake.wait(0.5)
            self.wake.clear()

    def download(self, job):
        job_id = job["id"]
        with self.lock:
            cancel = self.cancel_events.setdefault(job_id, threading.Event())
        process = None
        try:
            for attempt in range(1, 3):
                output, final_path = [], None
                with self.lock:
                    if cancel.is_set() or self.stopping.is_set():
                        return
                    existing = self.existing(job["video_id"], job["mode"], job["folder"]) if job["skip_duplicates"] else None
                    if existing:
                        job.update(status="skipped", detail="Already saved", path=existing)
                        return
                    if attempt == 1:
                        job["started_at"] = time.time()
                    command = self.engine.download_command(job)
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=CREATE_FLAGS)
                    self.processes[job_id] = process
                    job.update(status="downloading", detail="Connecting to YouTube…", attempt=attempt, error_code="", speed_bps=0, eta_seconds=None, progress=0)
                for line in process.stdout:
                    with self.lock:
                        if cancel.is_set() or self.stopping.is_set():
                            break
                        if line.startswith("OFFBEAT_PROGRESS "):
                            try:
                                progress = json.loads(line[len("OFFBEAT_PROGRESS "):])
                                total = progress.get("total_bytes") or progress.get("total_bytes_estimate") or 0
                                percent = min(99, (progress.get("downloaded_bytes", 0) / total * 100)) if total else 0
                                speed, eta = progress.get("speed") or 0, progress.get("eta")
                                job.update(speed_bps=speed, eta_seconds=eta, progress_at=time.time(), progress=round(percent, 1), detail=(f"{speed / 1048576:.1f} MB/s" + (f" · {int(eta)}s remaining" if eta else "")) if speed else "Downloading…")
                                if progress.get("status") == "finished":
                                    job.update(status="converting", detail="Finishing your file…", progress=99, speed_bps=0, eta_seconds=None)
                                else:
                                    job["status"] = "downloading"
                            except (ValueError, TypeError):
                                pass
                        elif line.startswith("OFFBEAT_PROCESS "):
                            job.update(status="converting", detail="Finishing your file…", progress=99, speed_bps=0, eta_seconds=None)
                        elif line.startswith("OFFBEAT_FILE "):
                            final_path = json.loads(line[len("OFFBEAT_FILE "):])
                        elif line.startswith("OFFBEAT_TITLE "):
                            job["title"] = json.loads(line[len("OFFBEAT_TITLE "):])
                        else:
                            output.append(line)
                            output = output[-30:]
                if cancel.is_set() or self.stopping.is_set():
                    stop_process(process)
                process.wait()
                process.stdout.close()
                with self.lock:
                    self.processes.pop(job_id, None)
                    if cancel.is_set() or self.stopping.is_set():
                        return
                    path = Path(final_path) if final_path else None
                    if process.returncode == 0 and path and path.is_file() and path.stat().st_size > 0:
                        job.update(status="done", elapsed_seconds=max(.01, time.time() - job["started_at"]), progress=100, detail="Saved to your library", path=str(path), error_code="")
                        self.state["library"].append({"id": job_id, "video_id": job["video_id"], "mode": job["mode"], "title": job["title"], "channel": job["channel"], "quality": job["quality"], "path": str(path), "saved": time.time(), "size": path.stat().st_size})
                        return
                    error = classify_error("".join(output))
                    delay = error["delay"]
                    if error["code"] == "rate_limit":
                        self.cooldown_until = max(self.cooldown_until, time.monotonic() + delay)
                    job.update(error_code=error["code"], detail=error["message"])
                    if not delay or attempt == 2:
                        job["status"] = "error"
                        return
                    job.update(status="retrying", detail=f"Retrying in {delay}s (attempt 2 of 2). " + error["message"])
                    self.save()
                if cancel.wait(delay):
                    return
        except Exception as exc:
            with self.lock:
                if not cancel.is_set() and not self.stopping.is_set():
                    job.update(status="error", detail=friendly_error(str(exc)), error_code="download")
        finally:
            if process:
                try:
                    stop_process(process)
                    process.wait(timeout=10)
                finally:
                    process.stdout.close()
            with self.lock:
                if self.stopping.is_set() and job["status"] in ACTIVE:
                    job.update(status="interrupted", detail="App closed. Retry to continue the partial download.")
                job.update(speed_bps=0, eta_seconds=None)
                self.processes.pop(job_id, None)
                self.cancel_events.pop(job_id, None)
                self.workers.pop(job_id, None)
                self.save()
                self.wake.set()

    def close(self):
        self.stopping.set()
        self.wake.set()
        with self.lock:
            for event in self.cancel_events.values():
                event.set()
            processes = list(self.processes.values())
            workers = list(self.workers.values())
        for process in processes:
            stop_process(process)
        if self.thread:
            self.thread.join(timeout=8)
        for worker in workers:
            worker.join(timeout=10)
        self.save()
