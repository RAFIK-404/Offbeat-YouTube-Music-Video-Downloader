import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import make_server
from engine import DownloadManager, Engine, normalize_url, classify_error

ID = "BaW_jenozKc"
ID2 = "jNQXAC9IVRw"


def item(video_id=ID, title="A song"):
    return {"video_id": video_id, "title": title, "channel": "Test artist", "duration": 10, "unavailable": False}


class FakeEngine:
    def __init__(self, folder):
        self.folder = folder
        self.fail = False
        self.delay = False
        self.calls = 0

    def health(self):
        return {"ready": True, "missing": []}

    def preview(self, url):
        return {"title": "My playlist", "items": [item()], "unavailable": 0, "is_playlist": True}

    def download_command(self, job):
        self.calls += 1
        extension = ".mp3" if job["mode"] == "audio" else ".mp4"
        path = self.folder / (job["id"] + extension)
        script = "import pathlib,time,json; "
        if self.delay:
            seconds = 30 if self.delay is True else self.delay
            script += "print('OFFBEAT_PROGRESS '+json.dumps({'downloaded_bytes':5,'total_bytes':10,'speed':100}),flush=True); " + f"time.sleep({seconds}); "
        if self.fail:
            script += "print('ERROR: Test network failure'); raise SystemExit(1)"
        else:
            script += f"pathlib.Path({str(path)!r}).write_bytes(b'valid-test-fixture'); print('OFFBEAT_FILE '+json.dumps({str(path)!r}))"
        return [sys.executable, "-c", script]


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = FakeEngine(self.root)
        self.manager = DownloadManager(self.root / "data", self.engine, self.root / "downloads")
        self.manager.settings({"folder": str(self.root / "downloads")})
        self.preview()

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def preview(self, entries=None):
        self.manager.preview_state = {"id": "preview", "status": "ready", "title": "Test playlist", "items": entries or [item()]}

    def add(self, ids=None):
        return self.manager.add("preview", ids or [ID])

    def finish(self):
        job = next(j for j in self.manager.state["jobs"] if j["status"] == "queued")
        self.manager.download(job)
        return job

    def wait_status(self, status, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.manager.snapshot()["jobs"][0]["status"] == status:
                return
            time.sleep(.05)
        self.fail(f"Did not reach {status}: {self.manager.snapshot()['jobs']}")

    def test_url_variants_and_playlist_scope(self):
        for url in [f"https://youtu.be/{ID}?si=abc", f"youtube.com/shorts/{ID}", f"https://music.youtube.com/watch?v={ID}"]:
            self.assertEqual(normalize_url(url), f"https://www.youtube.com/watch?v={ID}")
        url = f"https://www.youtube.com/watch?v={ID}&list=PLabc123"
        self.assertIn("playlist?list=PLabc123", normalize_url(url))
        self.assertIn("watch?v=", normalize_url(url, False))
        for url in ["https://youtube.com.evil.test/watch?v="+ID, "file:///etc/passwd", "http://localhost/test", "https://youtube.com@evil.test/watch?v="+ID, "https://youtube.com/watch?v=bad"]:
            with self.assertRaises(ValueError):
                normalize_url(url)

    def test_unavailable_preview_and_timeout_have_readable_errors(self):
        import subprocess
        engine = Engine(self.root)
        engine.base_command = lambda: ["yt-dlp"]
        with patch("engine.subprocess.run", return_value=SimpleNamespace(stdout="null\n", stderr="ERROR: This video is unavailable")):
            with self.assertRaisesRegex(ValueError, "unavailable"):
                engine.preview("https://www.youtube.com/watch?v=" + ID)
        with patch("engine.subprocess.run", side_effect=subprocess.TimeoutExpired("yt-dlp", 180)):
            with self.assertRaisesRegex(ValueError, "took too long"):
                engine.preview("https://www.youtube.com/watch?v=" + ID)

    def test_large_playlist_keeps_all_items(self):
        entries = [item(f"{i:011d}") for i in range(1500)]
        self.preview(entries)
        self.assertEqual(self.add([e["video_id"] for e in entries]), {"added": 1500, "skipped": 0})
        self.assertEqual(len(self.manager.snapshot()["jobs"]), 1500)

    def test_duplicate_in_same_playlist_and_queue(self):
        self.preview([item(), item(), item(ID2)])
        self.assertEqual(self.add([ID, ID2]), {"added": 2, "skipped": 1})
        self.assertEqual(self.add([ID]), {"added": 0, "skipped": 2})

    def test_success_persists_and_skips_across_restarts(self):
        self.add()
        job = self.finish()
        self.assertEqual(job["status"], "done")
        other = DownloadManager(self.root / "data", self.engine, self.root / "downloads")
        other.preview_state = self.manager.preview_state
        self.assertEqual(other.add("preview", [ID]), {"added": 0, "skipped": 1})
        self.assertEqual(len(other.snapshot()["library"]), 1)

    def test_audio_and_video_are_separate(self):
        self.add(); self.finish()
        self.manager.settings({"mode": "video"})
        self.assertEqual(self.add()["added"], 1)
        self.finish()
        self.assertEqual(len(self.manager.state["library"]), 2)

    def test_deleted_file_downloads_again(self):
        self.add()
        job = self.finish()
        Path(job["path"]).unlink()
        self.assertFalse(self.manager.snapshot()["library"][0]["exists"])
        self.assertEqual(self.add()["added"], 1)

    def test_renamed_title_and_preexisting_id_file(self):
        folder = self.root / "downloads" / "Music"
        folder.mkdir(parents=True)
        (folder / f"Completely different title [{ID}].mp3").write_bytes(b"content")
        self.assertEqual(self.add(), {"added": 0, "skipped": 1})

    def test_failure_does_not_poison_duplicate_history(self):
        self.engine.fail = True
        self.add()
        job = self.finish()
        self.assertEqual(job["status"], "error")
        self.assertEqual(self.manager.state["library"], [])
        self.engine.fail = False
        self.manager.action("retry", job["id"])
        self.finish()
        self.assertEqual(job["status"], "done")

    def test_worker_pause_resume_cancel_retry(self):
        self.manager.action("pause")
        self.add()
        self.engine.delay = True
        self.manager.start()
        time.sleep(.2)
        self.assertEqual(self.manager.state["jobs"][0]["status"], "queued")
        self.manager.action("resume")
        self.wait_status("downloading")
        job = self.manager.state["jobs"][0]
        self.manager.action("cancel", job["id"])
        deadline = time.monotonic() + 8
        while self.manager.workers and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertEqual(job["status"], "cancelled")
        self.assertEqual(self.manager.state["library"], [])
        self.engine.delay = False
        self.manager.action("retry", job["id"])
        self.wait_status("done")

    def test_interrupted_restart_is_safe(self):
        self.add()
        self.manager.state["jobs"][0]["status"] = "downloading"
        self.manager.save()
        other = DownloadManager(self.root / "data", self.engine, self.root / "downloads")
        self.assertTrue(other.state["paused"])
        self.assertEqual(other.state["jobs"][0]["status"], "interrupted")

    def test_skipping_can_be_disabled_without_overwriting(self):
        self.manager.settings({"skip_duplicates": False})
        self.preview([item(), item()])
        self.assertEqual(self.add(), {"added": 2, "skipped": 0})
        command = Engine(self.root).download_command
        # Inspect the real command with dependency validation stubbed.
        engine = Engine(self.root)
        engine.base_command = lambda: ["yt-dlp"]
        job = self.manager.state["jobs"][0]
        args = engine.download_command(job)
        self.assertIn(job["id"][:8], args[args.index("--output") + 1])
        self.assertIn("--no-overwrites", args)

    def test_settings_validate_quality_and_path(self):
        for change in [{"mode":"shell"}, {"video_quality":"999"}, {"folder":"relative"}, {"skip_duplicates":"false"}, {"concurrent_downloads":0}, {"concurrent_downloads":7}, {"concurrent_downloads":True}, {"concurrent_downloads":"3"}]:
            with self.assertRaises(ValueError):
                self.manager.settings(change)

    def until(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.manager.lock:
                if predicate():
                    return
            time.sleep(.03)
        self.fail("Condition not reached: " + repr(self.manager.snapshot()["jobs"]))

    def many(self, count=5):
        entries = [item(f"{i:011d}") for i in range(count)]
        self.preview(entries)
        self.add([entry["video_id"] for entry in entries])

    def test_parallel_limit_cancel_isolation_and_close(self):
        self.many()
        self.engine.delay = True
        self.manager.start()
        self.until(lambda: len(self.manager.processes) == 3)
        jobs = self.manager.state["jobs"]
        with self.manager.lock:
            survivors = {key: p.pid for key, p in self.manager.processes.items() if key != jobs[0]["id"]}
        self.manager.action("pause")
        self.manager.action("cancel", jobs[0]["id"])
        self.until(lambda: len(self.manager.workers) == 2)
        with self.manager.lock:
            self.assertEqual({key: p.pid for key,p in self.manager.processes.items()}, survivors)
            self.assertTrue(all(p.poll() is None for p in self.manager.processes.values()))
        self.assertEqual([j["status"] for j in jobs[3:]], ["queued", "queued"])
        self.manager.close()
        self.assertFalse(self.manager.processes)
        self.assertFalse(self.manager.workers)
        self.assertEqual([j["status"] for j in jobs], ["cancelled", "interrupted", "interrupted", "queued", "queued"])

    def test_parallel_live_limit_and_pause_finish(self):
        self.many()
        self.engine.delay = .8
        self.manager.settings({"concurrent_downloads": 1})
        self.manager.start()
        self.until(lambda: len(self.manager.processes) == 1)
        self.manager.settings({"concurrent_downloads": 3})
        self.until(lambda: len(self.manager.processes) == 3)
        self.manager.action("pause")
        self.until(lambda: not self.manager.workers)
        self.assertEqual(sum(j["status"] == "done" for j in self.manager.state["jobs"]), 3)
        self.assertEqual(sum(j["status"] == "queued" for j in self.manager.state["jobs"]), 2)
        self.manager.settings({"concurrent_downloads": 1})
        self.manager.action("resume")
        self.until(lambda: len(self.manager.processes) == 1)
        self.until(lambda: all(j["status"] == "done" for j in self.manager.state["jobs"]))
        self.assertEqual(len(self.manager.snapshot()["library"]), 5)

    def test_parallel_retry_duplicates_do_not_race(self):
        self.add()
        self.manager.state["jobs"][0]["status"] = "error"
        self.add()
        self.manager.state["jobs"][1]["status"] = "error"
        self.engine.delay = .3
        self.manager.action("retry_failed")
        self.manager.start()
        self.until(lambda: all(j["status"] in {"done", "skipped"} for j in self.manager.state["jobs"]))
        self.assertEqual(self.engine.calls, 1)
        self.assertEqual(len(self.manager.state["library"]), 1)

    def test_transient_error_retries_once_and_can_recover(self):
        command = self.engine.download_command
        def fail_once(job):
            self.engine.fail = self.engine.calls == 0
            return command(job)
        self.engine.download_command = fail_once
        self.add()
        job = self.finish()
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["attempt"], 2)
        self.assertEqual(len(self.manager.state["library"]), 1)

    def test_cancel_during_retry_backoff(self):
        self.engine.fail = True
        self.add()
        self.manager.start()
        self.wait_status("retrying")
        self.manager.action("cancel", self.manager.state["jobs"][0]["id"])
        self.until(lambda: not self.manager.workers)
        self.assertEqual(self.engine.calls, 1)
        self.assertEqual(self.manager.state["jobs"][0]["status"], "cancelled")

    def test_v1_settings_migrate_without_losing_queue_or_folder(self):
        self.add()
        self.manager.state.pop("setup_complete")
        self.manager.state["settings"].pop("concurrent_downloads")
        self.manager.save()
        other = DownloadManager(self.root / "data", self.engine, self.root / "different")
        self.assertEqual(other.state["settings"]["concurrent_downloads"], 3)
        self.assertEqual(other.state["settings"]["folder"], str(self.root / "downloads"))
        self.assertEqual(len(other.state["jobs"]), 1)
        self.assertTrue(other.state["paused"])
        self.assertTrue(other.state["setup_complete"])

    def test_error_reasons_are_not_mislabeled(self):
        cases = [
            ("ERROR: Requested format is not available", "format", False),
            ("ERROR: Private video. Sign in if granted access", "private", False),
            ("ERROR: account has been terminated", "removed", False),
            ("ERROR: Video unavailable. This video is not available", "unavailable", True),
            ("ERROR: Sign in to confirm you're not a bot", "sign_in", False),
            ("ERROR: HTTP Error 429: Too Many Requests", "rate_limit", True),
            ("ERROR: Connection timed out", "network", True),
        ]
        for message, code, retry in cases:
            result = classify_error(message)
            self.assertEqual(result["code"], code)
            self.assertEqual(bool(result["delay"]), retry)
        self.assertNotIn("private", classify_error(cases[0][0])["message"].lower())

    def test_flat_metadata_does_not_block_download_attempt(self):
        engine = Engine(self.root)
        engine.base_command = lambda: ["yt-dlp"]
        data = {"_type":"playlist", "entries":[{"id":ID, "title":"[Private video]", "availability":"private"}, {"id":ID2}, {"id":"00000000001", "live_status":"is_upcoming"}]}
        with patch("engine.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(data), stderr="")):
            items = engine.preview("url")["items"]
        self.assertFalse(items[0]["unavailable"])
        self.assertFalse(items[1]["unavailable"])
        self.assertEqual(items[1]["availability_note"], "Check on download")
        self.assertTrue(items[2]["unavailable"])

    def test_http_auth_origin_and_input_validation(self):
        server = make_server(self.manager, "secret", folder_picker=lambda: str(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/api/state")
            self.assertEqual(error.exception.code, 403)
            headers = {"X-Offbeat-Token":"secret", "Content-Type":"application/json"}
            with urlopen(Request(base + "/api/state", headers=headers)) as response:
                self.assertIn("settings", json.load(response))
            with urlopen(Request(base + "/api/choose-folder", data=b'{}', headers=headers)) as response:
                self.assertEqual(json.load(response)["folder"], str(self.root))
            request = Request(base + "/api/action", data=b'{"action":"pause"}', headers={**headers, "Origin":"https://evil.test"})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)
            self.assertFalse(self.manager.state["paused"])
        finally:
            server.shutdown()
            server.server_close()

    @unittest.skipUnless(os.name == "nt", "Windows single-instance guard")
    def test_second_app_instance_exits_cleanly(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        data = self.root / "instance-data"
        connection = self.root / "instance.json"
        command = [sys.executable, str(app), "--headless", "--data-dir", str(data), "--downloads", str(self.root / "media")]
        first = subprocess.Popen(command + ["--connection-file", str(connection)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not connection.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(connection.exists())
            result = subprocess.run(command, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            first.terminate()
            first.communicate(timeout=5)


class FirstRunTests(unittest.TestCase):
    def test_setup_waits_for_a_valid_folder_and_survives_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = FakeEngine(root)
            manager = DownloadManager(root / "data", engine, root / "suggested")
            self.assertFalse(manager.snapshot()["setup_complete"])
            manager.settings({"audio_quality":"192"})
            self.assertFalse(manager.snapshot()["setup_complete"])
            with self.assertRaisesRegex(ValueError, "Choose where"):
                manager.add("preview", [ID])
            manager.close()
            manager = DownloadManager(root / "data", engine, root / "suggested")
            self.assertFalse(manager.snapshot()["setup_complete"])
            chosen = root / "My music and videos"
            manager.settings({"folder":str(chosen)})
            self.assertTrue(chosen.is_dir())
            self.assertEqual(list(chosen.iterdir()), [])
            self.assertTrue(manager.snapshot()["setup_complete"])
            manager.close()
            manager = DownloadManager(root / "data", engine, root / "different-default")
            self.assertTrue(manager.snapshot()["setup_complete"])
            self.assertEqual(manager.snapshot()["settings"]["folder"], str(chosen))
            manager.preview_state = {"id":"preview", "status":"ready", "title":"Test", "items":[item()]}
            manager.add("preview", [ID])
            self.assertEqual(manager.snapshot()["jobs"][0]["folder"], str(chosen))
            manager.close()

    def test_unwritable_choice_does_not_complete_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = DownloadManager(root / "data", FakeEngine(root), root / "suggested")
            with patch("engine.Path.write_bytes", side_effect=PermissionError("Denied")):
                with self.assertRaisesRegex(ValueError, "not writable"):
                    manager.settings({"folder":str(root / "blocked")})
            self.assertFalse(manager.snapshot()["setup_complete"])
            self.assertEqual(manager.snapshot()["settings"]["folder"], str(root / "suggested"))
            manager.close()

    def test_cancelled_picker_does_not_complete_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = DownloadManager(root / "data", FakeEngine(root), root / "suggested")
            server = make_server(manager, "test-token", folder_picker=lambda: None)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                request = Request(f"http://127.0.0.1:{server.server_port}/api/choose-folder", data=b'{}', headers={"X-Offbeat-Token":"test-token", "Content-Type":"application/json"})
                with urlopen(request) as response:
                    self.assertIsNone(json.load(response)["folder"])
                self.assertFalse(manager.snapshot()["setup_complete"])
            finally:
                server.shutdown()
                server.server_close()
                manager.close()


if __name__ == "__main__":
    unittest.main()
