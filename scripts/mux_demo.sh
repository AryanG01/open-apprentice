#!/bin/sh
# Lays each narration clip (beats.json) over the Playwright video at its recorded start time. Optional "sped": [[from_s, to_s,
# factor], ...] in beats.json time-lapses long waits (say so in the narration). Usage: mux_demo.sh <ffmpeg> [dir]
set -e
FF="$1"; D="${2:-results/demo_video}"
V=$(ls "$D"/video/*.webm | head -1)
python3 - "$FF" "$D" "$V" <<'PY'
import json, os, subprocess, sys
ff, d, v = sys.argv[1:4]
meta = json.load(open(f"{d}/beats.json"))
b, sped = meta["beats"], meta.get("sped", [])
total = float(subprocess.run([ff, "-i", v], capture_output=True, text=True).stderr.split("Duration: ")[1].split(",")[0].split(":")[2]) + 60 * int(subprocess.run([ff, "-i", v], capture_output=True, text=True).stderr.split("Duration: ")[1].split(",")[0].split(":")[1])
cuts, t = [], 0.0
for a, z, f in sorted(sped):
    cuts += [(t, a, 1.0), (a, z, float(f))]; t = z
cuts.append((t, total, 1.0))
def newt(x):
    out = 0.0
    for a, z, f in cuts:
        if x <= a: break
        out += (min(x, z) - a) / f
    return out
vf = "".join(f"[0:v]trim={a}:{z},setpts=(PTS-STARTPTS)/{f}[v{i}];" for i, (a, z, f) in enumerate(cuts))
vf += "".join(f"[v{i}]" for i in range(len(cuts))) + f"concat=n={len(cuts)}:v=1:a=0[v]"
off, end = int(os.environ.get("OA_AUDIO_OFFSET_MS", "0")), 0.0
starts = []
for x in b:  # narration is sequential: a clip never starts before the previous one ended
    s = max(newt(x["start"]), end + 0.3); starts.append(s); end = s + x["secs"]
cmd = [ff, "-y", "-i", v] + [a for x in b for a in ("-i", f"{d}/audio/{x['file']}")]
fc = vf + ";" + "".join(f"[{i+1}:a]adelay={int(s*1000+off)}|{int(s*1000+off)}[a{i}];" for i, s in enumerate(starts))
fc += "".join(f"[a{i}]" for i in range(len(b))) + f"amix=inputs={len(b)}:normalize=0[a]"
cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-b:a", "160k", f"{d}/open_apprentice_demo.mp4"]
subprocess.run(cmd, check=True)
PY
echo "wrote $D/open_apprentice_demo.mp4"
