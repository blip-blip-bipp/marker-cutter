# Marker Cutter

A standalone desktop app (macOS and Windows) that cuts a multitrack recording from a
**Waves Tracks Live** session into per-song audio files, using the session's markers.
Each marker starts a song and the next marker ends it.

It reads the saved `.tracks` session file and the session's source WAVs and writes **new** files
elsewhere. It never modifies your session or your recordings, and Tracks Live does not need to be open.

> Unofficial. Not affiliated with or endorsed by Waves Audio. The `.tracks` format was worked out by
> inspecting session files, so a future Tracks Live version could change it.

## Get the app

There are no tagged releases yet. Builds come from the **Build app** GitHub Action
(Actions tab → *Build app* → latest run → *Artifacts*), or you can build it yourself (see
[Build it yourself](#build-it-yourself)).

| Platform | Status |
|---|---|
| macOS (Apple Silicon) | Built and tested locally: launches, loads a session, exports files. About 25 MB. |
| Windows (x64) | Builds successfully on GitHub Actions (about 13 MB zip). **Not yet run on a real Windows machine.** |

Known issues:

- The GitHub-hosted macOS job currently does not start for this repository (GitHub reports the macOS
  runner configuration as unsupported), so the macOS app is built locally for now.
- The apps are **not notarized or code-signed with a developer certificate**. macOS blocks the first
  launch (System Settings → Privacy & Security → *Open Anyway*) and Windows SmartScreen shows a warning
  (*More info → Run anyway*). A paid Apple Developer ID and a Windows code-signing certificate remove
  those prompts.
- On Windows the window uses the Microsoft Edge WebView2 runtime (normally already installed on current
  Windows 10/11).

## Features

- Lists the session's markers as songs, with start / end / length and a timeline strip whose song names
  wrap onto up to three lines.
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
- Styled to match the Tracks Live colour scheme.

## Using it

1. Open the app and click **Load session…**, then choose the session's `.tracks` file. It reopens the
   last session you used next time.
2. Tick the songs and tracks you want. Choose how the files are named, the export folder, and any
   pre/post-roll.
3. Click **Export**. If files already exist you are asked before anything is overwritten.

Per-user settings (the last session) are stored in `~/Library/Application Support/MarkerCutter`
(macOS) or `%APPDATA%\MarkerCutter` (Windows).

## Build it yourself

Needs Python 3 (use 3.12 or 3.13 on Windows). The packages are [pywebview](https://pywebview.flowrl.com/)
for the native window and [PyInstaller](https://pyinstaller.org/) for packaging.

```bash
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-app.txt
python3 marker_cutter/app.py                               # run the app from source
pyinstaller --noconfirm packaging/marker_cutter.spec       # build dist/Marker Cutter.app (or dist\Marker Cutter\ on Windows)
```

To let GitHub build it instead: Actions tab → **Build app** → *Run workflow* (or push to the
`standalone-app` branch, which also triggers it). The workflow file only offers the manual button once it
exists on the default branch.

## Browser version (no install needed)

The same app also runs in a browser using only the Python standard library:

```bash
python3 marker_cutter/server.py /path/to/MySession      # folder or the .tracks file
```

Then open <http://127.0.0.1:8765>. Without a path it reopens the last session you used. The
**Load session…** / **Choose…** buttons use the native file dialogs on macOS only; elsewhere pass the
session path on the command line.

On macOS you can build a double-clickable launcher for this version (stops any old copy, starts the
server, opens the page):

```bash
./macos/build_launcher.sh            # creates "Marker Cutter.app" here; drag it to your Dock
```

It points at this folder, so re-run the script if you move it. Server log: `~/Library/Logs/MarkerCutter.log`.

The server only listens on `127.0.0.1`, only answers requests addressed to localhost, and only exports
for requests that come from its own page.

## Command line

`split_at_markers.py` is the engine behind the app and works on its own:

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
- Full exports are large (every track × every song), so check free disk space; the app shows an estimate.
- Output WAVs carry audio only (no `bext`/`smpl` metadata from the originals).

## Layout

```
split_at_markers.py        session parser + WAV slicing engine, and the command-line tool
marker_cutter/app.py       native window (pywebview) around the local server and page
marker_cutter/server.py    local web server (stdlib only) wrapping the engine
marker_cutter/index.html   the GUI (plain HTML/CSS/JS)
packaging/                 PyInstaller spec for the native app
macos/                     alternative: double-clickable launcher that opens the browser version
.github/workflows/         builds the macOS and Windows apps on GitHub
```
