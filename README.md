# Marker Cutter

Cut a multitrack recording from a **Waves Tracks Live** session into per-song audio files, using the
session's markers. Each marker starts a song and the next marker ends it.

It reads the saved `.tracks` session file and the session's source WAVs and writes **new** files
elsewhere. It never modifies your session or your recordings, and Tracks Live does not need to be open.

> Unofficial. Not affiliated with or endorsed by Waves Audio. The `.tracks` format was worked out by
> inspecting session files, so a future Tracks Live version could change it.

## Features

- Lists the session's markers as songs, with start / end / length and a timeline strip.
- **Pick songs**: tick any number of songs (Select all / Deselect all) and export them in one run.
- **Pick tracks**: *All tracks* (untick any to skip), *Mono track*, or *Stereo pair*
  (interleaves two mono tracks into one stereo file).
- Everything starts unselected, so nothing is exported by accident.
- **File naming**: click tags to add them, drag to reorder: session name, marker name, session
  creation date, marker start time, marker number (`001`), track number, track name.
  Joined with `_`. Duplicate names across the batch are caught before exporting.
- Optional pre-roll / post-roll (ms), a subfolder per song, and an estimated size before you export.
- Handles tracks made of several clips (for example a bounced take after the main recording).
- Output is plain WAV at the source sample rate and bit depth.

## Requirements

- Python 3 (tested on 3.14). Standard library only, nothing to install.
- macOS for the **Load session…** / **Choose…** buttons (they use the native file dialogs) and the
  launcher app. On other systems you can still type a session path on the command line.

## Quick start (GUI)

```bash
python3 marker_cutter/server.py /path/to/MySession      # folder or the .tracks file
```

Then open <http://127.0.0.1:8765>. Without a path it reopens the last session you used.

For a double-clickable launcher on macOS (stops any old copy, starts the server, opens the page):

```bash
./macos/build_launcher.sh            # creates "Marker Cutter.app" here; drag it to your Dock
```

The app points at this folder, so re-run the script if you move it. Server log:
`~/Library/Logs/MarkerCutter.log`.

The server only listens on `127.0.0.1`, only answers requests addressed to localhost, and only
exports for requests that come from its own page.

## Native app (macOS and Windows)

A real desktop window instead of a browser tab, built with [pywebview](https://pywebview.flowrl.com/)
and [PyInstaller](https://pyinstaller.org/). Use Python 3.12 or 3.13 on Windows.

```bash
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-app.txt
python3 marker_cutter/app.py                               # run it from source
pyinstaller --noconfirm packaging/marker_cutter.spec       # build dist/Marker Cutter.app (or dist\Marker Cutter\ on Windows)
```

Or let GitHub build both: Actions tab → **Build app** → *Run workflow*, then download the zips from
the run's artifacts (`macos-arm64`, `windows-x64`).

Sharing the result: the apps are **not notarized or code-signed with a developer certificate**, so
macOS blocks the first launch (System Settings → Privacy & Security → *Open Anyway*) and Windows
SmartScreen shows a warning (*More info → Run anyway*). A paid Apple Developer ID and a Windows
code-signing certificate remove those prompts.

Per-user settings (the last session) are stored in `~/Library/Application Support/MarkerCutter`
(macOS) or `%APPDATA%\MarkerCutter` (Windows).

## Command line

`split_at_markers.py` is the engine behind the GUI and works on its own:

```bash
python3 split_at_markers.py SESSION                  # dry run: lists songs and times, writes nothing
python3 split_at_markers.py SESSION --pick           # choose tracks and songs interactively
python3 split_at_markers.py SESSION --run --out ~/Desktop/my-songs
python3 split_at_markers.py SESSION --run --tracks "1-12,27" --songs "3,5-8"
python3 split_at_markers.py SESSION --run --tracks "all -15,-16" --songs "all -17"
```

Run with `-h` for all options.

## Notes

- It reads the **last saved** state, so save in Tracks Live after adding or moving markers.
- Tracks Live rewrites a session's `created` date on every save, so "session creation date" uses the
  earliest date found in the session file and its `Session File Backups`.
- Full exports are large (every track × every song), so check free disk space; the GUI shows an estimate.
- Output WAVs carry audio only (no `bext`/`smpl` metadata from the originals).

## Layout

```
split_at_markers.py        session parser + WAV slicing engine, and the command-line tool
marker_cutter/server.py    local web server (stdlib only) wrapping the engine
marker_cutter/index.html   the GUI (plain HTML/CSS/JS)
marker_cutter/app.py       native window (pywebview) around the same server and page
packaging/                 PyInstaller spec for the native app
macos/                     alternative: double-clickable launcher that opens the browser version
.github/workflows/         builds the macOS and Windows apps on GitHub
```
