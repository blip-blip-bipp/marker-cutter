#!/usr/bin/env python3
"""
split_at_markers.py - split a Waves Tracks Live session into per-song WAV files
at the session's markers.

Non-destructive: it only READS the .tracks file and the source WAVs, and writes
new files into a separate output folder. Safe to run while Tracks Live has the
session open (it reads the last saved state, so Save in Tracks Live first if you
just added or moved markers).

Output layout:
    <out>/<NN Marker name>/<Track name>.wav     (one folder per song, all tracks)
or with --by-track:
    <out>/<Track name>/<NN Marker name>.wav

Each marker starts a song; a song ends at the next marker (the last one runs to
the end of the recording). Timeline gaps / multiple clips on a track are handled
(gaps are filled with silence, muted clips are skipped).

Usage:
    split_at_markers.py SESSION_DIR_OR_.tracks_FILE            # dry run (default)
    split_at_markers.py SESSION --run                          # actually write files
    split_at_markers.py SESSION --run --out ~/Desktop/my-songs
    split_at_markers.py SESSION --pick                         # choose tracks & songs interactively (dry run)
    split_at_markers.py SESSION --pick --run                   # ...and export your choice
    split_at_markers.py SESSION --run --tracks "1-12,27" --songs "3,5-8"   # by number / range
    split_at_markers.py SESSION --run --tracks "all -15,-16" --songs "all -17"  # everything except some
    split_at_markers.py SESSION --run --tracks "m Click,LR" --songs 3,4,5  # tracks by exact name
    split_at_markers.py SESSION --min-seconds 10               # merge sections shorter than 10 s (default 10)
"""
import argparse
import glob
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

CHUNK = 4 * 1024 * 1024


# ----------------------------------------------------------------- WAV helpers
def read_wav_info(path):
    """Return (channels, rate, bits, fmt_tag, data_offset, data_bytes) for a PCM/float WAV."""
    with open(path, "rb") as f:
        head = f.read(12)
        if head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
            raise ValueError(f"not a WAV file: {path}")
        fmt = None
        while True:
            h = f.read(8)
            if len(h) < 8:
                raise ValueError(f"no data chunk: {path}")
            cid, sz = h[:4], struct.unpack("<I", h[4:])[0]
            if cid == b"fmt ":
                body = f.read(sz)
                tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
                if tag == 0xFFFE and sz >= 26:  # WAVE_FORMAT_EXTENSIBLE -> real tag in subformat
                    tag = struct.unpack("<H", body[24:26])[0]
                fmt = (ch, rate, bits, tag)
                if sz & 1:
                    f.read(1)
            elif cid == b"data":
                off = f.tell()
                size = sz
                if sz == 0xFFFFFFFF or off + sz > os.path.getsize(path):
                    size = os.path.getsize(path) - off
                if fmt is None:
                    raise ValueError(f"data before fmt: {path}")
                return (*fmt, off, size)
            else:
                f.seek(sz + (sz & 1), 1)


def wav_header(ch, rate, bits, tag, nbytes):
    block = ch * bits // 8
    hdr = b"RIFF" + struct.pack("<I", 36 + nbytes) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, tag, ch, rate, rate * block, block, bits)
    hdr += b"data" + struct.pack("<I", nbytes)
    return hdr


def copy_bytes(src, start, n, dst):
    src.seek(start)
    while n > 0:
        buf = src.read(min(CHUNK, n))
        if not buf:
            raise IOError("unexpected end of source file")
        dst.write(buf)
        n -= len(buf)


def write_zeros(dst, n):
    z = bytes(min(CHUNK, n)) if n else b""
    while n > 0:
        k = min(len(z), n)
        dst.write(z[:k])
        n -= k


# --------------------------------------------------------------- session parse
def load_session(arg):
    path = arg
    if os.path.isdir(arg):
        files = [p for p in glob.glob(os.path.join(arg, "*.tracks"))]
        if not files:
            sys.exit(f"No .tracks file in {arg}")
        path = files[0]
    root = ET.parse(path).getroot()
    base = os.path.dirname(os.path.abspath(path))
    sr = int(root.find("SessionInfo").get("sampleRate", "48000"))

    markers = []
    marker_el = root.find("Markers")            # a session saved before any markers were added has no Markers section
    for m in (marker_el if marker_el is not None else []):
        markers.append((int(m.get("position")), m.get("name") or "", int(m.get("number", "0"))))
    markers.sort()

    tracks = []
    for tr in root.find("Tracks"):
        clips = []
        for c in tr.iter("Clip"):
            if c.get("muted") == "1":
                continue
            clips.append(dict(
                file=os.path.join(base, c.get("file")),
                start=int(c.get("startSample")),
                offset=int(c.get("offsetSamples")),
                length=int(c.get("lengthSamples")),
            ))
        clips.sort(key=lambda c: c["start"])
        tracks.append(dict(name=tr.get("name") or "Track", clips=clips))

    end = max((c["start"] + c["length"] for t in tracks for c in t["clips"]), default=0)
    return path, base, sr, markers, tracks, end


def build_songs(markers, end, sr, min_seconds):
    """Sections [start,end). Sections shorter than min_seconds are merged into the following one
    (the earlier marker wins, so duplicate/accidental markers don't create stub files)."""
    pts = [list(m) for m in markers]
    i = 0
    dropped = []
    while i < len(pts) - 1:
        if (pts[i + 1][0] - pts[i][0]) < min_seconds * sr:
            dropped.append(pts.pop(i + 1))
        else:
            i += 1
    songs = []
    for k, (pos, name, num) in enumerate(pts):
        stop = pts[k + 1][0] if k + 1 < len(pts) else end
        songs.append(dict(index=k + 1, number=num, name=name, start=pos, end=stop))
    # a too-short final section gets absorbed into the previous song
    if len(songs) > 1 and (songs[-1]["end"] - songs[-1]["start"]) < min_seconds * sr:
        dropped.append([songs[-1]["start"], songs[-1]["name"], songs[-1]["number"]])
        songs.pop()
        songs[-1]["end"] = end
    return songs, dropped


def safe(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name or "untitled"


def fmt_time(samples, sr):
    s = samples / sr
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"


# ----------------------------------------------------------------------- export
def export_segment(track, a, b, out_path):
    """Write timeline range [a,b) of one track to out_path. Returns False if track has no audio there."""
    spans = [c for c in track["clips"] if c["start"] < b and c["start"] + c["length"] > a]
    if not spans:
        return False
    info = read_wav_info(spans[0]["file"])
    ch, rate, bits, tag = info[:4]
    frame = ch * bits // 8
    nframes = b - a
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".part"
    with open(tmp, "wb") as dst:
        dst.write(wav_header(ch, rate, bits, tag, nframes * frame))
        pos = a
        for c in spans:
            cs = max(a, c["start"])
            ce = min(b, c["start"] + c["length"])
            if cs > pos:
                write_zeros(dst, (cs - pos) * frame)
            cinfo = read_wav_info(c["file"])
            if cinfo[:4] != info[:4]:
                raise ValueError(f"format mismatch between clips on track '{track['name']}'")
            file_start = cinfo[4] + (c["offset"] + (cs - c["start"])) * frame
            with open(c["file"], "rb") as src:
                copy_bytes(src, file_start, (ce - cs) * frame, dst)
            pos = ce
        if pos < b:
            write_zeros(dst, (b - pos) * frame)
    os.replace(tmp, out_path)
    return True


class SegmentReader:
    """Sequential frame reader over timeline range [a,b) of one track (clips + silence for gaps)."""

    def __init__(self, track, a, b):
        self.name = track["name"]
        self.spans = [c for c in track["clips"] if c["start"] < b and c["start"] + c["length"] > a]
        self.pos, self.b, self.i = a, b, 0
        self.fh, self.fh_clip, self.cinfo = None, None, None
        self.info = read_wav_info(self.spans[0]["file"])[:4] if self.spans else None
        self.frame = self.info[0] * self.info[2] // 8 if self.info else 0

    def read(self, nframes):
        out = []
        need = min(nframes, self.b - self.pos)
        while need > 0:
            while self.i < len(self.spans) and self.spans[self.i]["start"] + self.spans[self.i]["length"] <= self.pos:
                self.i += 1
            if self.i >= len(self.spans) or self.spans[self.i]["start"] > self.pos:
                gap_end = self.spans[self.i]["start"] if self.i < len(self.spans) else self.b
                k = min(need, gap_end - self.pos)
                out.append(bytes(k * self.frame))
            else:
                c = self.spans[self.i]
                if self.fh_clip is not c:
                    if self.fh:
                        self.fh.close()
                    self.cinfo = read_wav_info(c["file"])
                    if self.cinfo[:4] != self.info:
                        raise ValueError(f"format mismatch between clips on track '{self.name}'")
                    self.fh, self.fh_clip = open(c["file"], "rb"), c
                k = min(need, c["start"] + c["length"] - self.pos)
                self.fh.seek(self.cinfo[4] + (c["offset"] + self.pos - c["start"]) * self.frame)
                data = self.fh.read(k * self.frame)
                if len(data) != k * self.frame:
                    raise IOError(f"unexpected end of source file on track '{self.name}'")
                out.append(data)
            self.pos += k
            need -= k
        return b"".join(out)

    def close(self):
        if self.fh:
            self.fh.close()
            self.fh = None


def export_pair(track_l, track_r, a, b, out_path):
    """Interleave two MONO tracks into one stereo WAV for timeline range [a,b)."""
    rl, rr = SegmentReader(track_l, a, b), SegmentReader(track_r, a, b)
    try:
        if rl.info is None and rr.info is None:
            return False
        if rl.info is None or rr.info is None:
            raise ValueError("both tracks of a stereo pair need audio in this range")
        if rl.info[0] != 1 or rr.info[0] != 1:
            raise ValueError("a stereo pair needs two MONO tracks (one chosen track is already stereo)")
        if rl.info != rr.info:
            raise ValueError("the two tracks have different sample rate / bit depth")
        _, rate, bits, tag = rl.info
        w = bits // 8
        nframes = b - a
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        tmp = out_path + ".part"
        step = CHUNK // (2 * w)
        with open(tmp, "wb") as dst:
            dst.write(wav_header(2, rate, bits, tag, nframes * 2 * w))
            done = 0
            while done < nframes:
                n = min(step, nframes - done)
                L, R = rl.read(n), rr.read(n)
                buf = bytearray(len(L) * 2)
                for k in range(w):
                    buf[k::2 * w] = L[k::w]
                    buf[w + k::2 * w] = R[k::w]
                dst.write(buf)
                done += n
        os.replace(tmp, out_path)
        return True
    finally:
        rl.close()
        rr.close()


def parse_selection(text, n):
    """Parse '1-5,8', 'all', 'all -3', '2,4-6 -5' into a sorted list of 1-based indices (1..n).
    Tokens starting with '-' (after whitespace) remove items; 'all' or '*' selects everything."""
    chosen = set()
    removed = set()
    for tok in re.split(r"[,\s]+", text.strip()):
        if not tok:
            continue
        neg = tok.startswith("-")
        body = tok[1:] if neg else tok
        if body.lower() in ("all", "*"):
            rng = set(range(1, n + 1))
        else:
            mm = re.fullmatch(r"(\d+)(?:-(\d+))?", body)
            if not mm:
                raise ValueError(f"can't read '{tok}'")
            lo = int(mm.group(1))
            hi = int(mm.group(2) or lo)
            if lo > hi:
                lo, hi = hi, lo
            if lo < 1 or hi > n:
                raise ValueError(f"'{tok}' is outside 1-{n}")
            rng = set(range(lo, hi + 1))
        (removed if neg else chosen).update(rng)
    if not chosen and removed:  # e.g. just "-3" means everything except 3
        chosen = set(range(1, n + 1))
    return sorted(chosen - removed)


def ask(prompt_title, labels):
    """Show a numbered list and loop until the user gives a valid selection."""
    print(f"\n{prompt_title}")
    width = len(str(len(labels)))
    for i, lab in enumerate(labels, 1):
        print(f"  {i:>{width}}  {lab}")
    while True:
        try:
            text = input("Choose (e.g. 1-12, 3,5, all, all -4)  [Enter = all]: ").strip()
        except EOFError:
            sys.exit("\nNo input available - use --tracks / --songs instead.")
        if not text:
            return list(range(1, len(labels) + 1))
        try:
            sel = parse_selection(text, len(labels))
            if sel:
                return sel
            print("  Nothing selected.")
        except ValueError as e:
            print(f"  {e}")


def select_by_arg(arg, items, names):
    """--tracks/--songs value: numbers/ranges ('1-5,8', 'all -3') or exact names (comma-separated)."""
    n = len(items)
    try:
        return [items[i - 1] for i in parse_selection(arg, n)]
    except ValueError:
        want = {x.strip().lower() for x in arg.split(",")}
        picked = [it for it, nm in zip(items, names) if nm.lower() in want]
        missing = want - {nm.lower() for nm in names}
        if missing:
            sys.exit(f"Unknown name(s): {', '.join(sorted(missing))}")
        return picked


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="session folder or .tracks file")
    ap.add_argument("--run", action="store_true", help="write files (default is a dry run)")
    ap.add_argument("--out", help="output folder (default: <session>/Song Splits)")
    ap.add_argument("--by-track", action="store_true", help="folder per track instead of per song")
    ap.add_argument("--pick", "-i", action="store_true",
                    help="interactive: show numbered tracks and songs and ask which to export")
    ap.add_argument("--tracks", help="tracks to include: numbers/ranges ('1-12,20', 'all -5') "
                                     "or exact names ('m Click,LR'); default all")
    ap.add_argument("--songs", help="songs to include by list number: '3,5-8', 'all -17'; default all")
    ap.add_argument("--min-seconds", type=float, default=10.0,
                    help="merge sections shorter than this into the next marker (default 10)")
    a = ap.parse_args()

    path, base, sr, markers, tracks, end = load_session(a.session)
    if not markers:
        sys.exit("No markers in session.")
    songs, dropped = build_songs(markers, end, sr, a.min_seconds)

    # --- choose tracks
    if a.pick and not a.tracks:
        sel = ask("TRACKS", [t["name"] for t in tracks])
        tracks = [tracks[i - 1] for i in sel]
    elif a.tracks:
        tracks = select_by_arg(a.tracks, tracks, [t["name"] for t in tracks])
    # --- choose songs (cuts)
    if a.pick and not a.songs:
        sel = ask("SONGS / CUTS", [f"{s['name']}  ({fmt_time(s['start'], sr)}, "
                                    f"{(s['end'] - s['start']) / sr / 60:.1f} min)" for s in songs])
        songs = [songs[i - 1] for i in sel]
    elif a.songs:
        songs = [songs[i - 1] for i in parse_selection(a.songs, len(songs))]
    if not tracks or not songs:
        sys.exit("Nothing selected.")

    out = a.out or os.path.join(base, "Song Splits")
    print(f"Session : {path}")
    print(f"Rate    : {sr} Hz   Tracks: {len(tracks)}   Songs: {len(songs)}   Output: {out}")
    print("Selected: " + ", ".join(t["name"] for t in tracks))
    for d in dropped:
        print(f"  note: marker '{d[1]}' at {fmt_time(d[0], sr)} is <{a.min_seconds:g}s after the previous one -> merged")
    print()
    for s in songs:
        print(f"  {s['index']:>2}  {fmt_time(s['start'], sr)} -> {fmt_time(s['end'], sr)}  "
              f"({(s['end'] - s['start']) / sr / 60:5.1f} min)  {s['name']}")
    if not a.run:
        print("\nDry run - nothing written. Add --run to export.")
        return

    total = 0
    for s in songs:
        label = f"{s['index']:02d} {safe(s['name'])}"
        for t in tracks:
            p = (os.path.join(out, safe(t["name"]), label + ".wav") if a.by_track
                 else os.path.join(out, label, safe(t["name"]) + ".wav"))
            if export_segment(t, s["start"], s["end"], p):
                total += 1
        print(f"  done: {label}")
    print(f"\nWrote {total} files to {out}")


if __name__ == "__main__":
    main()
