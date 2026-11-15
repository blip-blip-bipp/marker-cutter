# PyInstaller spec for the native app (macOS and Windows). Build from the repo root with:
#     pyinstaller --noconfirm packaging/marker_cutter.spec
# Output: dist/Marker Cutter.app (macOS) or dist/Marker Cutter/ (Windows).
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))   # SPECPATH is provided by PyInstaller
APP_DIR = os.path.join(ROOT, "marker_cutter")
ICON_DIR = os.path.join(ROOT, "packaging", "icons")    # regenerate with packaging/make_icons.swift + make_ico.py
ICNS = os.path.join(ICON_DIR, "AppIcon.icns")          # macOS app icon
ICO = os.path.join(ICON_DIR, "AppIcon.ico")            # Windows .exe icon

a = Analysis(
    [os.path.join(APP_DIR, "app.py")],
    pathex=[ROOT, APP_DIR],                              # split_at_markers.py lives in ROOT
    datas=[(os.path.join(APP_DIR, "index.html"), ".")],  # server.py looks for index.html next to itself
    hiddenimports=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Marker Cutter", console=False,
          icon=ICO if sys.platform == "win32" else None)   # on macOS the icon belongs to the .app bundle below
coll = COLLECT(exe, a.binaries, a.datas, name="Marker Cutter")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Marker Cutter.app",
        icon=ICNS,
        bundle_identifier="com.markercutter.app",
        info_plist={
            "CFBundleShortVersionString": "1.5",
            "NSHighResolutionCapable": True,
            # shown in the macOS permission prompts when the app first touches these locations
            "NSDesktopFolderUsageDescription": "Marker Cutter saves exported audio to a folder you choose.",
            "NSDocumentsFolderUsageDescription": "Marker Cutter reads your Tracks Live sessions and saves exports.",
            "NSRemovableVolumesUsageDescription": "Marker Cutter reads session audio from external drives.",
            "NSNetworkVolumesUsageDescription": "Marker Cutter reads session audio from network volumes.",
        },
    )
