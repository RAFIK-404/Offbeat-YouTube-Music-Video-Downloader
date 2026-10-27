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
import zipfile

from test_engine import FakeEngine, item, ID
from components import ComponentInstaller, REQUIRED
from engine import DownloadManager, Engine


class Reply(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {'Content-Length':str(len(data))}


class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.installer = ComponentInstaller(self.root / 'bin')

    def tearDown(self):
        self.temp.cleanup()

    def test_release_rejects_missing_digest_and_unofficial_url(self):
        asset = {'name':'yt-dlp.exe','browser_download_url':'https://example.com/program.exe','digest':'sha256:' + 'a' * 64}
        payload = {'tag_name':'2026.10.26','assets':[asset]}
        with patch('components.urlopen',return_value=Reply(json.dumps(payload).encode())):
            with self.assertRaises(ValueError):
                self.installer.release('yt-dlp/yt-dlp','yt-dlp.exe')
        asset['browser_download_url'] = 'https://github.com/yt-dlp/yt-dlp/releases/download/2026.10.26/yt-dlp.exe'
        asset['digest'] = ''
        with patch('components.urlopen',return_value=Reply(json.dumps(payload).encode())):
            with self.assertRaises(ValueError):
                self.installer.release('yt-dlp/yt-dlp','yt-dlp.exe')

    def test_corrupt_download_never_reaches_installed_tools(self):
        self.installer.bindir.mkdir()
        original = self.installer.bindir / 'yt-dlp.exe'
        original.write_bytes(b'previous')
        with patch.object(self.installer,'release',return_value={'url':'https://github.com/test','sha256':'a' * 64}), patch('components.urlopen',return_value=Reply(b'corrupt')), patch.object(self.installer,'verify') as verify:
            with self.assertRaisesRegex(ValueError,'verification'):
                self.installer.install(threading.Event(),lambda *args:None)
        self.assertEqual(original.read_bytes(),b'previous')
        verify.assert_not_called()
        self.assertEqual(list(self.root.glob('.offbeat-setup-*')),[])

    def test_cancelled_setup_preserves_existing_files(self):
        self.installer.bindir.mkdir()
        (self.installer.bindir / 'old.dll').write_bytes(b'old')
        stop = threading.Event()
        stop.set()
        with self.assertRaisesRegex(ValueError,'interrupted'):
            self.installer.install(stop,lambda *args:None)
        self.assertEqual((self.installer.bindir / 'old.dll').read_bytes(),b'old')

    def test_archive_paths_cannot_escape_staging(self):
        archive = self.root / 'archive.zip'
        stage = self.root / 'stage'
        stage.mkdir()
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('../../deno.exe',b'verified executable fixture')
            z.writestr('../../outside.txt',b'no')
        self.installer.unpack(archive,stage,('deno.exe',))
        self.assertTrue((stage / 'deno.exe').is_file())
        self.assertFalse((self.root / 'outside.txt').exists())

    def test_missing_or_duplicate_executables_are_rejected(self):
        archive = self.root / 'archive.zip'
        stage = self.root / 'stage'
        stage.mkdir()
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('readme.txt',b'no executable')
        with self.assertRaisesRegex(ValueError,'incomplete'):
            self.installer.unpack(archive,stage,('deno.exe',))
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('one/deno.exe',b'one')
            z.writestr('two/deno.exe',b'two')
        with self.assertRaisesRegex(ValueError,'Unexpected'):
            self.installer.unpack(archive,stage,('deno.exe',))

    def install_fixture(self, fail_commit=False):
        def release(repo, filename):
            return {'project':repo,'version':'test','url':'https://github.com/fixture','sha256':'a' * 64}
        def download(release, target, stopping, progress):
            if target.suffix == '.exe':
                target.write_bytes(b'new')
            else:
                with zipfile.ZipFile(target,'w') as z:
                    names = ('deno.exe',) if 'deno' in target.name else ('ffmpeg.exe','ffprobe.exe','runtime.dll')
                    for name in names:
                        z.writestr('package/bin/' + name,b'new')
        from components import os
        original_replace = os.replace
        def replace(src, dest):
            if fail_commit and Path(src).name == 'bin' and Path(src).parent.name.startswith('.offbeat-setup-'):
                raise PermissionError('test install failure')
            return original_replace(src,dest)
        with patch.object(self.installer,'release',side_effect=release), patch.object(self.installer,'download',side_effect=download), patch.object(self.installer,'verify') as verify, patch('components.os.replace',side_effect=replace):
            result = self.installer.install(threading.Event(),lambda *args:None)
            verify.assert_called_once()
            return result

    def test_complete_set_is_installed_together_and_manifest_recorded(self):
        result = self.install_fixture()
        self.assertEqual(len(result),3)
        self.assertTrue(all((self.installer.bindir / name).is_file() for name in REQUIRED))
        self.assertEqual(len(json.loads((self.installer.bindir / 'tools-manifest.json').read_text())),3)

    def test_commit_failure_rolls_back_previous_directory(self):
        self.installer.bindir.mkdir()
        (self.installer.bindir / 'old.dll').write_bytes(b'previous')
        with self.assertRaises(PermissionError):
            self.install_fixture(True)
        self.assertEqual((self.installer.bindir / 'old.dll').read_bytes(),b'previous')

    def test_executable_checks_require_successful_output(self):
        with patch('components.subprocess.run',return_value=SimpleNamespace(returncode=1,stdout=b'')):
            with self.assertRaisesRegex(ValueError,'could not start'):
                self.installer.verify(self.root)

    def test_manager_retries_failed_setup_and_blocks_downloads_until_ready(self):
        engine = FakeEngine(self.root)
        engine.health = lambda:{'ready':(self.root / 'ready').exists(),'missing':[]}
        manager = DownloadManager(self.root / 'data',engine,self.root / 'downloads')
        manager.settings({'folder':str(self.root / 'downloads')})
        started = threading.Event()
        finish = threading.Event()
        class Installer:
            calls = 0
            def install(inner, stopping, progress):
                inner.calls += 1
                if inner.calls == 1:
                    raise ValueError('test connection failure')
                started.set()
                finish.wait(3)
                (self.root / 'ready').write_bytes(b'yes')
        installer = Installer()
        manager.component_installer = installer
        manager.preview_state = {'id':'test','status':'ready','items':[item()],'title':'Test'}
        manager.add('test',[ID])
        manager.start()
        try:
            manager.setup_components()
            manager.component_thread.join(3)
            self.assertEqual(manager.snapshot()['components']['status'],'error')
            manager.setup_components()
            self.assertTrue(started.wait(2))
            manager.setup_components()
            self.assertEqual(installer.calls,2)
            self.assertEqual(manager.state['jobs'][0]['status'],'queued')
            with self.assertRaises(ValueError):
                manager.preview('https://youtu.be/' + ID)
            with self.assertRaises(ValueError):
                manager.update_downloader('check')
            finish.set()
            manager.component_thread.join(3)
            deadline = time.monotonic() + 5
            while manager.state['jobs'][0]['status'] != 'done' and time.monotonic() < deadline:
                time.sleep(.03)
            self.assertEqual(manager.state['jobs'][0]['status'],'done')
            self.assertEqual(manager.snapshot()['components']['status'],'ready')
        finally:
            finish.set()
            manager.close()
