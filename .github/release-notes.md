Standalone desktop app that cuts a **Waves Tracks Live** session into per-song WAV files at its markers.
It reads the saved `.tracks` file and the session's audio, and writes new files; your session and
recordings are never modified.

## What's new in v1.7

- **Exports go to the session's `Rendered Files` folder by default** (the folder Tracks Live creates next to
  `Audio Files`). Choose another folder any time, and use **Back to default** to return.
- **Clear messages when a session can't be opened**, instead of a raw error: for example when the last
  session is on a drive that isn't connected, with a **Try again** button.
- **Sessions with no markers** no longer crash the app; it tells you to add markers in Tracks Live first.

Earlier: v1.6 added the new app icon on macOS and Windows.

## Downloads

| File | For |
|---|---|
| `MarkerCutter-macos-arm64.zip` | Macs with Apple silicon (M1 or later) |
| `MarkerCutter-windows-x64.zip` | Windows, 64-bit |

## First launch

These builds are **not code-signed or notarized**, so the operating system warns on the first run.

- **macOS:** unzip, move `Marker Cutter.app` to Applications and open it. If it is blocked, go to
  System Settings → Privacy & Security and click **Open Anyway**.
- **Windows:** unzip the folder and run `Marker Cutter.exe`. If SmartScreen appears, choose
  **More info → Run anyway**. The window uses the Microsoft Edge WebView2 runtime, which current
  Windows 10/11 normally already has.

## Status

- macOS: a local build of this same code was tested on Apple silicon (opens a session, lists songs and
  tracks, exports). This downloadable build is produced by GitHub Actions from the same recipe.
- Windows: the build succeeds on GitHub Actions but **has not yet been run on a real Windows machine**.

See the [README](https://github.com/blip-blip-bipp/marker-cutter#readme) for features and usage.
