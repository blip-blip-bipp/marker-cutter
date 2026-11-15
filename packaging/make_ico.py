#!/usr/bin/env python3
"""Join the PNGs in <icons>/win/ into a multi-size Windows AppIcon.ico (PNG-compressed entries, Vista+).

    python3 packaging/make_ico.py packaging/icons
"""
import os
import struct
import sys

icons = sys.argv[1] if len(sys.argv) > 1 else "icons"
win = os.path.join(icons, "win")
sizes = sorted(int(f[5:-4]) for f in os.listdir(win) if f.startswith("icon_") and f.endswith(".png"))
if not sizes:
    sys.exit(f"no icon_<size>.png files in {win}")

images = []
for n in sizes:
    with open(os.path.join(win, f"icon_{n}.png"), "rb") as f:
        images.append((n, f.read()))

header = struct.pack("<HHH", 0, 1, len(images))      # reserved, type=icon, count
offset = 6 + 16 * len(images)
directory, blobs = b"", b""
for n, data in images:
    dim = 0 if n >= 256 else n                        # 0 means 256 in the ICO directory
    directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
    blobs += data

out = os.path.join(icons, "AppIcon.ico")
with open(out, "wb") as f:
    f.write(header + directory + blobs)
print(f"wrote {out} ({len(images)} sizes: {', '.join(str(s) for s in sizes)})")
