"""Offbeat desktop app. --headless exposes the same UI for browser testing."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from engine import DownloadManager, Engine

ROOT = Path(__file__).resolve().parent
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT


def make_server(manager, token, port=0, folder_picker=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, content_type="application/json"):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8") if content_type == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' https://i.ytimg.com data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def authorized(self):
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected_host:
                self.send(403, {"error": "Invalid host"})
                return False
            if not secrets.compare_digest(self.headers.get("X-Offbeat-Token", ""), token):
                self.send(403, {"error": "Open Offbeat from the desktop app."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + expected_host:
                self.send(403, {"error": "Invalid origin"})
                return False
            return True

        def do_GET(self):
            route = urlparse(self.path).path
            if route.startswith("/api/"):
                if not self.authorized():
                    return
                if route == "/api/state":
                    state = manager.snapshot()
                    state["desktop"] = folder_picker is not None
                    self.send(200, state)
                else:
                    self.send(404, {"error": "Not found"})
                return
            files = {"/": "index.html", "/index.html": "index.html", "/app.css": "app.css", "/app.js": "app.js", "/favicon.svg": "favicon.svg"}
            if route not in files:
                self.send(404, {"error": "Not found"})
                return
            path = ROOT / "web" / files[route]
            self.send(200, path.read_bytes(), (mimetypes.guess_type(str(path))[0] or "text/plain") + "; charset=utf-8")

        def do_POST(self):
            if not self.authorized():
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected JSON request.")
                size = int(self.headers.get("Content-Length", "0"))
                if size < 0 or size > 2_000_000:
                    raise ValueError("Request is too large.")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object.")
                route = urlparse(self.path).path
                if route == "/api/settings":
                    result = manager.settings(data)
                elif route == "/api/preview":
                    result = manager.preview(str(data.get("url", "")), bool(data.get("whole_playlist", True)))
                elif route == "/api/queue":
                    result = manager.add(data.get("preview_id"), data.get("video_ids"))
                elif route == "/api/playlists":
                    if data.get("action") == "save":
                        result = manager.save_playlists(data.get("preview_id"))
                    else:
                        result = manager.playlist_action(data.get("action"), data.get("id"))
                elif route == "/api/update":
                    result = manager.update_downloader(data.get("action"))
                elif route == "/api/action":
                    manager.action(data.get("action"), data.get("id"))
                    result = {"ok": True}
                elif route == "/api/choose-folder":
                    if folder_picker is None:
                        raise ValueError("Enter the full folder path. Browse is available in the desktop app.")
                    result = {"folder": folder_picker()}
                elif route == "/api/open-folder":
                    path = Path(manager.snapshot()["settings"]["folder"])
                    if data.get("id"):
                        record = next((item for item in manager.snapshot()["library"] if item["id"] == data["id"]), None)
                        if not record:
                            raise ValueError("This file is not in your library.")
                        path = Path(record["path"]).parent
                    path.mkdir(parents=True, exist_ok=True)
                    os.startfile(str(path))
                    result = {"ok": True}
                else:
                    self.send(404, {"error": "Not found"})
                    return
                self.send(200, result or {"ok": True})
            except (ValueError, OSError, TypeError, KeyError) as exc:
                self.send(400, {"error": str(exc)})
            except Exception:
                self.send(500, {"error": "Something went wrong. Please try again."})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


class FolderPicker:
    def __init__(self):
        self.window = None

    def choose_folder(self):
        import webview
        result = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--downloads", type=Path)
    parser.add_argument("--connection-file", type=Path)
    args = parser.parse_args()
    # Portable by default: the application writes only beside itself and inside
    # the user-selected destination. Each portable copy has its own library.
    data_dir = args.data_dir or APP_ROOT / "data"
    destination = args.downloads or APP_ROOT / "Downloads"
    data_dir.mkdir(parents=True, exist_ok=True)
    instance_lock = (data_dir / ".instance.lock").open("a+b")
    if os.name == "nt":
        import msvcrt
        if os.fstat(instance_lock.fileno()).st_size == 0:
            instance_lock.write(b"0")
            instance_lock.flush()
        instance_lock.seek(0)
        try:
            msvcrt.locking(instance_lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            if not args.headless:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, "Offbeat is already open. Switch to its existing window.", "Offbeat", 64)
            instance_lock.close()
            return
    manager = DownloadManager(data_dir, Engine(APP_ROOT), destination)
    token = secrets.token_urlsafe(32)
    picker = FolderPicker()
    server = make_server(manager, token, args.port, picker.choose_folder if not args.headless else None)
    url = f"http://127.0.0.1:{server.server_port}/#token={token}"
    if args.connection_file:
        args.connection_file.write_text(json.dumps({"url": url, "token": token, "port": server.server_port}), encoding="utf-8")
    manager.start()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        if args.headless:
            print(url, flush=True)
            threading.Event().wait()
        else:
            import webview
            picker.window = webview.create_window("Offbeat", url, width=1220, height=860, min_size=(860, 650), background_color="#141814", confirm_close=True)
            webview.start(gui="edgechromium", private_mode=True)
    except KeyboardInterrupt:
        pass
    finally:
        manager.close()
        server.shutdown()
        server.server_close()
        instance_lock.close()


if __name__ == "__main__":
    main()
