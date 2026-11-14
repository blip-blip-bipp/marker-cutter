#!/usr/bin/env python3
"""
Marker Cutter as a native desktop app (macOS / Windows).

A pywebview window around the same local server and page the browser version uses. The server only
binds 127.0.0.1 on a random free port, so it never clashes with another copy and isn't reachable
from other machines.

    pip install -r requirements-app.txt
    python3 marker_cutter/app.py [SESSION_FOLDER_OR_.tracks]
"""
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import webview  # noqa: E402  (pywebview)
import server   # noqa: E402


def _first(result):
    """pywebview returns None, a path, or a tuple/list of paths depending on version and dialog."""
    if not result:
        return ""
    return result[0] if isinstance(result, (list, tuple)) else result


def main():
    srv, port = server.start_server(0)                       # 0 = any free port
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    window = webview.create_window("Marker Cutter", f"http://127.0.0.1:{port}/",
                                   width=1280, height=900, min_size=(940, 640))

    # pywebview >= 5 uses the FileDialog enum; older versions use module constants
    fd = getattr(webview, "FileDialog", None)
    open_dialog = fd.OPEN if fd else webview.OPEN_DIALOG
    folder_dialog = fd.FOLDER if fd else webview.FOLDER_DIALOG

    server.set_dialogs(
        session=lambda: _first(window.create_file_dialog(
            open_dialog, allow_multiple=False, file_types=("Tracks Live session (*.tracks)",))),
        folder=lambda: _first(window.create_file_dialog(folder_dialog)),
    )

    webview.start()                                           # blocks until the window is closed
    srv.shutdown()


if __name__ == "__main__":
    main()
