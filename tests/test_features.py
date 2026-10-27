import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_engine import FakeEngine, item, ID, ID2
from engine import DownloadManager
from overview import queue_overview
from updates import DownloaderUpdater

ID3 = "00000000003"
PLAYLIST_A = "https://www.youtube.com/playlist?list=PLone"
PLAYLIST_B = "https://www.youtube.com/playlist?list=PLtwo"


class PlaylistEngine(FakeEngine):
    def __init__(self, folder):
        super().__init__(folder)
        self.previews = {
            PLAYLIST_A:{"title":"First playlist", "items":[item(), item(ID2)], "is_playlist":True},
            PLAYLIST_B:{"title":"Second playlist", "items":[item(ID2), item(ID3)], "is_playlist":True},
            "https://www.youtube.com/watch?v=" + ID:{"title":"Single song", "items":[item()], "is_playlist":False},
        }
        self.checked = []

    def preview(self, url):
        self.checked.append(url)
        if url not in self.previews:
            raise ValueError("Test playlist is unavailable")
        return copy.deepcopy(self.previews[url])


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = PlaylistEngine(self.root)
        self.manager = DownloadManager(self.root / "data", self.engine, self.root / "media")
        self.manager.settings({"folder":str(self.root / "media"), "audio_quality":"192"})

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def until(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            with self.manager.lock:
                if predicate():
                    return
            time.sleep(.02)
        self.fail(repr(self.manager.snapshot()))

    def preview(self, urls=PLAYLIST_A):
        self.manager.preview(urls)
        self.until(lambda: self.manager.preview_state["status"] != "loading")
        return self.manager.preview_state

    def save_playlist(self, urls=PLAYLIST_A):
        preview = self.preview(urls)
        return self.manager.save_playlists(preview["id"])

    def sync(self, playlist):
        self.manager.playlist_action("download_new", playlist["id"])
        self.until(lambda: playlist["sync_status"] != "loading")
        return playlist.get("last_result")

    def test_multiple_links_merge_overlaps_and_keep_partial_results(self):
        preview = self.preview(f"{PLAYLIST_A}\n{PLAYLIST_B}\nhttps://youtu.be/{ID}\n{PLAYLIST_A}\nhttps://www.youtube.com/watch?v={ID3}\nhttps://example.com/bad")
        self.assertEqual(preview["status"], "ready")
        self.assertEqual([i["video_id"] for i in preview["items"]], [ID, ID2, ID3])
        self.assertEqual(preview["duplicates"], 2)
        self.assertEqual(len(preview["errors"]), 2)
        self.assertEqual(len(self.engine.checked), 4)
        self.assertEqual(preview["checked"], 4)
        self.assertEqual(self.manager.add(preview["id"], [ID, ID2, ID3]), {"added":3, "skipped":0})

    def test_batch_limits_and_all_failed(self):
        with self.assertRaisesRegex(ValueError, "50"):
            self.manager.preview(' '.join([PLAYLIST_A] * 51))
        with self.assertRaisesRegex(ValueError, "No valid"):
            self.manager.preview("https://example.com")
        preview = self.preview("https://www.youtube.com/watch?v=" + ID3)
        self.assertEqual(preview["status"], "error")
        self.assertIn("unavailable", preview["error"])

    def test_download_new_restores_missing_files_and_remembers_preferences(self):
        self.save_playlist()
        playlist = self.manager.state["playlists"][0]
        self.assertEqual(self.sync(playlist), {"added":2, "skipped":0})
        for job in list(self.manager.state["jobs"]):
            self.manager.download(job)
        self.assertTrue(all(j["status"] == "done" for j in self.manager.state["jobs"]))
        Path(self.manager.state["jobs"][0]["path"]).unlink()
        self.engine.previews[PLAYLIST_A]["items"].append(item(ID3))
        self.manager.settings({"mode":"video", "folder":str(self.root / "elsewhere"), "skip_duplicates":False})
        self.assertEqual(self.sync(playlist), {"added":2, "skipped":1})
        new = self.manager.state["jobs"][-2:]
        self.assertEqual({j["video_id"] for j in new}, {ID, ID3})
        self.assertTrue(all(j["mode"] == "audio" and j["quality"] == "192" and j["folder"] == str(self.root / "media") and j["skip_duplicates"] for j in new))
        self.assertEqual(self.sync(playlist), {"added":0, "skipped":3})
        self.assertEqual(len(self.manager.state["jobs"]), 4)
        self.assertEqual(self.manager.state["settings"]["mode"], "video")

    def test_overlapping_saved_playlists_skip_queued_items_and_persist(self):
        self.assertEqual(self.save_playlist(PLAYLIST_A + '\n' + PLAYLIST_B), {"saved":2})
        first, second = self.manager.state["playlists"]
        self.assertEqual(self.sync(first), {"added":2, "skipped":0})
        self.assertEqual(self.sync(second), {"added":1, "skipped":1})
        self.manager.close()
        other = DownloadManager(self.root / "data", self.engine, self.root / "other")
        self.assertEqual(len(other.state["playlists"]), 2)
        self.assertEqual(len(other.state["jobs"]), 3)
        other.close()

    def test_resaving_updates_preferences_and_remove_preserves_files(self):
        self.save_playlist()
        self.manager.settings({"audio_quality":"320"})
        self.save_playlist()
        self.assertEqual(len(self.manager.state["playlists"]), 1)
        self.assertEqual(self.manager.state["playlists"][0]["quality"], "320")
        keep = self.root / "media/keep.mp3"
        keep.write_bytes(b"media")
        self.manager.playlist_action("remove", self.manager.state["playlists"][0]["id"])
        self.assertEqual(self.manager.state["playlists"], [])
        self.assertTrue(keep.exists())

    def test_failed_playlist_refresh_preserves_saved_entry(self):
        self.save_playlist()
        playlist = self.manager.state["playlists"][0]
        self.engine.previews.pop(PLAYLIST_A)
        self.sync(playlist)
        self.assertEqual(playlist["sync_status"], "error")
        self.assertEqual(playlist["title"], "First playlist")
        self.assertEqual(self.manager.state["jobs"], [])

    def test_update_blocks_starts_and_previews_until_finished(self):
        began, finish = threading.Event(), threading.Event()
        class StubUpdater:
            def check(self):
                return {"current":"2026.01.01", "latest":"2026.02.01", "available":True}
            def install(self, release, stopping, progress):
                began.set()
                finish.wait(5)
                return release["latest"]
        self.manager.updater = StubUpdater()
        self.manager.update_downloader("check")
        self.until(lambda: self.manager.update_state["status"] == "available")
        preview = self.preview()
        self.manager.add(preview["id"], [ID])
        try:
            self.manager.update_downloader("install")
            self.assertTrue(began.wait(2))
            self.manager.start()
            with self.assertRaisesRegex(ValueError, "updating"):
                self.manager.preview(PLAYLIST_B)
            time.sleep(.1)
            self.assertEqual(self.engine.calls, 0)
        finally:
            finish.set()
        self.until(lambda: self.manager.state["jobs"][0]["status"] == "done")
        self.assertEqual(self.manager.update_state["current"], "2026.02.01")

    def test_install_rejects_active_downloads(self):
        self.manager.updater = object()
        self.manager.update_release = {"available":True}
        self.manager.workers["busy"] = None
        try:
            with self.assertRaisesRegex(ValueError, "Pause"):
                self.manager.update_downloader("install")
        finally:
            self.manager.workers.clear()


class UpdateTests(unittest.TestCase):
    def response(self, data):
        response = io.BytesIO(data)
        response.headers = {"Content-Length":str(len(data))}
        return response

    def test_corrupt_download_leaves_installed_binary_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "yt-dlp.exe"
            binary.write_bytes(b"original")
            updater = DownloaderUpdater(binary)
            release = {"url":"https://github.com/test", "latest":"2026.02.01", "sha256":"0"*64}
            with patch("updates.urlopen", return_value=self.response(b"corrupt")), patch.object(updater, "version") as version:
                with self.assertRaisesRegex(ValueError, "verification failed"):
                    updater.install(release, threading.Event(), lambda _: None)
                version.assert_not_called()
            self.assertEqual(binary.read_bytes(), b"original")
            self.assertEqual(list(Path(directory).glob('yt-dlp-update-*')), [])

    def test_verified_download_is_replaced_only_after_version_check(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "yt-dlp.exe"
            binary.write_bytes(b"original")
            updater = DownloaderUpdater(binary)
            payload = b"verified fixture"
            release = {"url":"https://github.com/test", "latest":"2026.02.01", "sha256":hashlib.sha256(payload).hexdigest()}
            def version(stage):
                self.assertEqual(binary.read_bytes(), b"original")
                self.assertEqual(stage.read_bytes(), payload)
                return release["latest"]
            with patch("updates.urlopen", return_value=self.response(payload)), patch.object(updater, "version", side_effect=version):
                updater.install(release, threading.Event(), lambda _: None)
            self.assertEqual(binary.read_bytes(), payload)

    def test_check_rejects_nonofficial_asset_and_missing_digest(self):
        updater = DownloaderUpdater(Path('unused'))
        for url, digest in [('https://evil.test/tool.exe','sha256:' + '0'*64), ('https://github.com/yt-dlp/yt-dlp/releases/download/2026.02.01/yt-dlp.exe','')]:
            release = {"tag_name":"2026.02.01", "assets":[{"name":"yt-dlp.exe", "browser_download_url":url, "digest":digest}]}
            with patch.object(updater, "version", return_value="2026.01.01"), patch("updates.urlopen", return_value=self.response(json.dumps(release).encode())):
                with self.assertRaisesRegex(ValueError, "verified"):
                    updater.check()

    def test_cancelled_update_keeps_original(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "yt-dlp.exe"
            binary.write_bytes(b"original")
            stop = threading.Event()
            stop.set()
            with patch("updates.urlopen", return_value=self.response(b"data")):
                with self.assertRaisesRegex(ValueError, "interrupted"):
                    DownloaderUpdater(binary).install({"url":"https://github.com/test"}, stop, lambda _: None)
            self.assertEqual(binary.read_bytes(), b"original")


class OverviewTests(unittest.TestCase):
    def state(self):
        base = {"mode":"audio", "folder":str(Path.cwd()), "duration":100}
        return {"paused":False, "settings":{"folder":str(Path.cwd()), "concurrent_downloads":2}, "jobs":[
            {**base, "status":"done", "elapsed_seconds":10},
            {**base, "status":"downloading", "speed_bps":2097152, "eta_seconds":8, "progress":50, "progress_at":time.time()},
            {**base, "status":"queued", "duration":200},
        ]}

    def test_aggregate_speed_progress_queue_estimate_and_disk(self):
        with patch('overview.shutil.disk_usage', return_value=SimpleNamespace(free=123456,total=987654)):
            overview = queue_overview(self.state())
        self.assertEqual(overview['speed_bps'], 2097152)
        self.assertEqual(overview['completed'], 1)
        self.assertEqual(overview['remaining'], 2)
        self.assertEqual(overview['progress'], 50)
        self.assertEqual(overview['eta_seconds'], 20)
        self.assertEqual(overview['disks'][0]['free'], 123456)

    def test_paused_unknown_and_stale_estimates_are_not_fabricated(self):
        state = self.state()
        state['paused'] = True
        state['jobs'][1]['progress_at'] = time.time() - 20
        self.assertIsNone(queue_overview(state)['eta_seconds'])
        self.assertEqual(queue_overview(state)['speed_bps'], 0)
        state['paused'] = False
        state['jobs'] = [state['jobs'][-1]]
        with patch('overview.shutil.disk_usage', side_effect=OSError()):
            overview = queue_overview(state)
        self.assertIsNone(overview['eta_seconds'])
        self.assertIsNone(overview['disks'][0]['free'])


if __name__ == '__main__':
    unittest.main()
