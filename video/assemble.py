"""Render every beat in its own process, then join them into one MP4 without re-encoding.

    python assemble.py ql      # draft  (480p15)
    python assemble.py qh      # final  (1080p60)

One process per beat avoids a spurious libav "No space left on device" that this machine hits after
~40 clips in a single long render. Clips are checked for matching size/fps, then remuxed in order.
"""
import pathlib
import subprocess
import sys

import av

from scenes import NAMES

HERE = pathlib.Path(__file__).parent
QUALITY_DIR = {"ql": "480p15", "qm": "720p30", "qh": "1080p60"}


def render(flag: str, name: str) -> pathlib.Path:
    log = HERE / "logs" / f"{name}_{flag}.log"
    log.parent.mkdir(exist_ok=True)
    with open(log, "w", encoding="utf-8") as fh:
        r = subprocess.run([sys.executable, "-m", "manim", f"-{flag}", "scenes.py", name], cwd=HERE, stdout=fh, stderr=subprocess.STDOUT)
    out = HERE / "media" / "videos" / "scenes" / QUALITY_DIR[flag] / f"{name}.mp4"
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"render failed: {name} (see {log})")
    return out


def join(clips, dst: pathlib.Path) -> float:
    shape, total = None, 0.0
    for p in clips:
        with av.open(str(p)) as c:
            v = c.streams.video[0]
            s = (v.codec_context.width, v.codec_context.height, round(float(v.average_rate)))
            dur = float(c.duration / av.time_base)
            total += dur
            print(f"  {p.stem:14s} {dur:6.2f} s  {s[0]}x{s[1]} @ {s[2]}")
            if shape is None:
                shape = s
            elif s != shape:
                raise SystemExit(f"mismatch: {p} is {s}, expected {shape}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(dst), "w") as out:
        ostream, offset = None, 0
        for p in clips:
            with av.open(str(p)) as inp:
                s = inp.streams.video[0]
                if ostream is None:
                    ostream = out.add_stream_from_template(s)
                last = 0
                for pkt in inp.demux(s):
                    if pkt.dts is None:
                        continue
                    pkt.dts += offset
                    pkt.pts += offset
                    last = max(last, pkt.pts + (pkt.duration or 0))
                    pkt.stream = ostream
                    out.mux(pkt)
                offset = last
    return total


def main(flag: str = "ql"):
    clips = []
    for name in NAMES:
        print(f"rendering {name} ({flag}) ...", flush=True)
        clips.append(render(flag, name))
    dst = HERE / "out" / f"bios_auth_explainer_{QUALITY_DIR[flag]}.mp4"
    total = join(clips, dst)
    print(f"joined {len(clips)} beats, {total:.1f} s -> {dst} ({dst.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main(*sys.argv[1:])
