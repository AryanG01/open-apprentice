"""capture/frames (Chrome screencast PNGs with timestamps) -> public/capture.mp4 at a constant 30 fps (each frame held until
the next one arrived), plus public/marks.json.   .venv/bin/python tools/encode.py"""

import json
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
CAP = ROOT / "capture"
frames = json.loads((CAP / "frames.json").read_text())
lines = []
for a, b in zip(frames, frames[1:] + [{"t": frames[-1]["t"] + 2.0}]):
    lines += [f"file 'frames/{a['file']}'", f"duration {max(0.001, b['t'] - a['t']):.3f}"]
lines.append(f"file 'frames/{frames[-1]['file']}'")
(CAP / "concat.txt").write_text("\n".join(lines) + "\n")
out = ROOT / "public/capture.mp4"
subprocess.run(
    [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(CAP / "concat.txt"),
     "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "14", "-preset", "medium",
     "-movflags", "+faststart", str(out)],
    check=True, cwd=CAP,
)
shutil.copy(CAP / "marks.json", ROOT / "public/marks.json")
print(f"{out} ({len(frames)} frames, {frames[-1]['t']:.0f}s)")
