#!/usr/bin/env python3
"""
Marker Cutter - local web GUI for split_at_markers.py (stdlib only, no installs).

    python3 server.py [SESSION_FOLDER_OR_.tracks]      # then open http://127.0.0.1:8765

Binds to 127.0.0.1 only. Reads the session and source WAVs; never modifies them.
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # import the existing backend: ../split_at_markers.py
import split_at_markers as core  # noqa: E402

PORT = int(os.environ.get("MARKER_CUTTER_PORT", "8765"))
ALLOWED_HOSTS = set()   # Host headers we answer; filled in once the server knows its real port


def user_data_dir():
    """Per-user, writable settings folder (the app bundle itself may be read-only)."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "MarkerCutter")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


LAST_FILE = os.path.join(user_data_dir(), "last_session.txt")   # remembers the last session between launches


def _read_last():
    try:
        with open(LAST_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


DEFAULT_SESSION = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else _read_last()


class NoMarkersError(Exception):
    """The session loaded fine but has nothing to cut."""


def session_render_dir(base):
    """Where exports go by default: the 'Rendered Files' folder Tracks Live creates inside every session
    (created on export if the session doesn't have one yet)."""
    return os.path.join(base, "Rendered Files")


def explain_load_error(path, exc):
    """Plain-language reason a session couldn't be opened (instead of a raw Python exception)."""
    p = os.path.expanduser(path)
    if isinstance(exc, NoMarkersError):
        return str(exc)
    if isinstance(exc, PermissionError):
        return ("Permission was denied. On macOS, allow Marker Cutter to access that folder or drive "
                "(System Settings → Privacy & Security → Files and Folders).")
    if isinstance(exc, FileNotFoundError) or not os.path.exists(p):
        return ("That file or folder wasn't found. It may have been moved or deleted, or it's on an "
                "external or network drive that isn't connected.")
    if isinstance(exc, (ET.ParseError, AttributeError, TypeError, KeyError)):
        return "That doesn't look like a readable Tracks Live session (.tracks) file."
    return f"{type(exc).__name__}: {exc}"


def session_created_date(tpath, base):
    """Tracks Live rewrites SessionInfo 'created' on every save, so the earliest value found in the
    session file and its Session File Backups is the real creation date. Returns YYYY-MM-DD or ''."""
    best = None
    for p in [tpath] + glob.glob(os.path.join(base, "Session File Backups", "*.tracks")):
        try:
            with open(p, "rb") as f:
                head = f.read(4096).decode("utf-8", "ignore")
        except OSError:
            continue
        m = re.search(r'created="(\d{4}-\d{2}-\d{2})T([\d:.]+)', head)
        if m and (best is None or (m.group(1), m.group(2)) < best):
            best = (m.group(1), m.group(2))
    return best[0] if best else ""


def hms_dash(seconds):
    s = int(seconds)
    return f"{s // 3600:02d}-{s % 3600 // 60:02d}-{s % 60:02d}"


FILENAME_TAGS = ("session", "marker", "date", "start", "marker_no", "track_no", "track")


def describe_session(path):
    """Everything the GUI needs: format info, tracks (with channel count), regions marker->next marker."""
    tpath, base, sr, markers, tracks, end = core.load_session(path)
    if not markers:
        raise NoMarkersError("This session has no markers yet. Add markers in Tracks Live, save the "
                             "session, then load it again.")
    bit_depth = None
    out_tracks = []
    for i, t in enumerate(tracks):
        ch = None
        if t["clips"]:
            try:
                info = core.read_wav_info(t["clips"][0]["file"])
                ch, bit_depth = info[0], info[2]
            except (OSError, ValueError):
                pass
        out_tracks.append({"index": i, "name": t["name"], "channels": ch, "clips": len(t["clips"])})

    regions = []
    for k, (pos, name, num) in enumerate(markers):
        stop = markers[k + 1][0] if k + 1 < len(markers) else end
        regions.append({"index": k, "number": num, "name": name, "start": pos, "end": stop,
                        "startSec": pos / sr, "endSec": stop / sr, "lenSec": (stop - pos) / sr})
    return {
        "path": tpath,
        "name": os.path.splitext(os.path.basename(tpath))[0],
        "sampleRate": sr,
        "bitDepth": bit_depth,
        "createdDate": session_created_date(tpath, base),
        "defaultOutDir": session_render_dir(base),      # Tracks Live's own "Rendered Files" folder in the session
        "totalSec": end / sr,
        "tracks": out_tracks,
        "regions": regions,
    }


DIALOGS = {"session": None, "folder": None}   # the native app window plugs its own pickers in here


def set_dialogs(session=None, folder=None):
    """Register file/folder pickers (each returns a path string, or '' if cancelled)."""
    DIALOGS["session"], DIALOGS["folder"] = session, folder


def pick_session_dialog():
    """Choose a .tracks file so the browser doesn't need a filesystem path."""
    if DIALOGS["session"]:
        return DIALOGS["session"]() or ""
    if sys.platform != "darwin":
        return ""   # plain-browser mode outside macOS: type the path on the command line instead
    script = ('POSIX path of (choose file with prompt "Choose a Tracks Live session (.tracks)" '
              'of type {"tracks", "public.data"})')
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _default_out():
    desktop = os.path.expanduser("~/Desktop")
    return os.path.join(desktop if os.path.isdir(desktop) else os.path.expanduser("~"), "Marker Cutter")


DEFAULT_OUT = _default_out()
JOBS = {}
JOBS_LOCK = threading.Lock()


def pick_folder_dialog():
    if DIALOGS["folder"]:
        return DIALOGS["folder"]() or ""
    if sys.platform != "darwin":
        return ""
    script = 'POSIX path of (choose folder with prompt "Choose the export folder")'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip().rstrip("/") if r.returncode == 0 else ""


def slug(s):
    return re.sub(r"\s+", "-", re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", s)).strip("-.") or "untitled"


def plan_export(req):
    """Validate the request and return (jobs, out_dir, session) where jobs = [(label, out_path, kind, tracks, a, b)]."""
    tpath, base, sr, markers, tracks, end = core.load_session(os.path.expanduser(req["path"]))
    name = os.path.splitext(os.path.basename(tpath))[0]
    raw = req.get("regions")
    ks = sorted({int(x) for x in (raw if raw is not None else [req["region"]])})   # one or many songs
    if not ks:
        raise ValueError("no songs selected")
    if any(not 0 <= k < len(markers) for k in ks):
        raise ValueError("unknown region")
    pre = max(0, int(float(req.get("preMs") or 0) * sr / 1000))
    post = max(0, int(float(req.get("postMs") or 0) * sr / 1000))

    idx = [int(i) for i in req["tracks"]]
    if not idx or any(not 0 <= i < len(tracks) for i in idx):
        raise ValueError("no tracks selected")
    mode = req["mode"]
    pattern = (req.get("pattern") or "").strip()
    if not pattern:
        raise ValueError("add at least one tag to the file name")
    unknown = set(re.findall(r"\{(\w+)\}", pattern)) - set(FILENAME_TAGS)
    if unknown:
        raise ValueError("unknown file name tag(s): " + ", ".join(sorted(unknown)))
    out_dir = os.path.expanduser(req.get("outDir") or session_render_dir(base))

    if mode == "stereo":
        if len(idx) != 2:
            raise ValueError("a stereo pair needs exactly two tracks")
        units = [("pair", [tracks[idx[0]], tracks[idx[1]]],
                  tracks[idx[0]]["name"] + "+" + tracks[idx[1]]["name"], f"{idx[0] + 1}+{idx[1] + 1}")]
    else:
        units = [("single", [tracks[i]], tracks[i]["name"], str(i + 1)) for i in idx]
    created = session_created_date(tpath, base)
    song_folders = bool(req.get("songFolders"))
    jobs, seen = [], set()
    for k in ks:
        pos, mname, mnum = markers[k]
        stop = markers[k + 1][0] if k + 1 < len(markers) else end
        a, b = max(0, pos - pre), min(end, stop + post)
        folder = os.path.join(out_dir, f"{mnum:03d} {core.safe(mname)}") if song_folders else out_dir
        for kind, trs, label, tno in units:
            vals = {"session": slug(name), "marker": slug(mname), "date": created or "undated",
                    "start": hms_dash(pos / sr), "marker_no": f"{mnum:03d}",
                    "track": slug(label), "track_no": tno}
            # single pass, so a marker/track name that happens to contain "{...}" is never re-expanded
            fname = re.sub(r"\{(\w+)\}", lambda m: vals[m.group(1)], pattern)
            fname = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", fname)
            if not fname.lower().endswith(".wav"):
                fname += ".wav"
            path = os.path.join(folder, fname)
            if path in seen:
                raise ValueError(f"two files would be named '{fname}' - add the marker number, start time "
                                 f"or track to the file name (or tick 'Subfolder per song')")
            seen.add(path)
            jobs.append((f"{mname} · {label}", path, kind, trs, a, b))
    return jobs, out_dir


def run_job(job_id, jobs):
    st = JOBS[job_id]
    try:
        for i, (label, path, kind, trs, a, b) in enumerate(jobs):
            st["current"] = label
            if kind == "pair":
                ok = core.export_pair(trs[0], trs[1], a, b, path)
            else:
                ok = core.export_segment(trs[0], a, b, path)
            if ok:
                st["files"].append(path)
            else:
                st["skipped"].append(label)
            st["done"] = i + 1
    except Exception as e:  # surface to the GUI
        st["error"] = f"{type(e).__name__}: {e}"
    finally:
        st["finished"] = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[marker-cutter] " + fmt % args + "\n")

    def _host_ok(self):
        # only answer requests addressed to localhost (blocks DNS-rebinding tricks)
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self.send_error(403)
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/job":
            q = urllib.parse.parse_qs(u.query)
            st = JOBS.get((q.get("id") or [""])[0])
            return self._json(st if st else {"error": "unknown job", "finished": True})
        if u.path == "/api/defaults":
            return self._json({"outDir": DEFAULT_OUT})
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/session":
            q = urllib.parse.parse_qs(u.query)
            path = (q.get("path") or [DEFAULT_SESSION])[0]
            if not path:
                return self._json({"error": "no-session"}, 200)
            try:
                info = describe_session(os.path.expanduser(path))
                try:
                    with open(LAST_FILE, "w") as f:
                        f.write(info["path"])
                except OSError:
                    pass
                self._json(info)
            except Exception as e:  # report to the GUI instead of crashing
                # kind: was this the remembered last session (auto-opened) or one the user just chose?
                self._json({"error": explain_load_error(path, e), "path": path,
                            "kind": "chosen" if q.get("path") else "remembered"}, 200)
        else:
            self.send_error(404)

    def do_POST(self):
        # state-changing: require our custom header (browsers can't send it cross-site without a preflight we refuse)
        if not self._host_ok() or self.headers.get("X-Marker-Cutter") != "1":
            return self.send_error(403)
        if self.path == "/api/pick":
            return self._json({"path": pick_session_dialog()})
        if self.path == "/api/pickdir":
            return self._json({"path": pick_folder_dialog()})
        if self.path == "/api/export":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                jobs, out_dir = plan_export(req)
                existing = [p for _, p, *_ in jobs if os.path.exists(p)]
                if existing and not req.get("overwrite"):
                    return self._json({"error": "exists", "existing": [os.path.basename(p) for p in existing],
                                       "outDir": out_dir})
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"})
            job_id = uuid.uuid4().hex[:12]
            with JOBS_LOCK:
                JOBS[job_id] = {"total": len(jobs), "done": 0, "current": "", "files": [], "skipped": [],
                                "error": None, "finished": False, "outDir": out_dir}
            threading.Thread(target=run_job, args=(job_id, jobs), daemon=True).start()
            return self._json({"job": job_id, "total": len(jobs), "outDir": out_dir})
        self.send_error(404)


def start_server(port=0):
    """Bind 127.0.0.1 (port 0 = any free port). Returns (server, port); caller runs serve_forever()."""
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    real = srv.server_address[1]
    ALLOWED_HOSTS.clear()
    ALLOWED_HOSTS.update({f"127.0.0.1:{real}", f"localhost:{real}"})
    return srv, real


if __name__ == "__main__":
    try:
        srv, port = start_server(PORT)
    except OSError:
        sys.exit(f"Port {PORT} is already in use - Marker Cutter is probably already running.\n"
                 f"Open http://127.0.0.1:{PORT} in your browser, or stop the old one first "
                 f"(macOS/Linux: kill $(lsof -nP -iTCP:{PORT} -sTCP:LISTEN -t)).")
    print(f"Marker Cutter running at http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
