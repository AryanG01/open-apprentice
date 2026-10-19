"""Narration: Kokoro-82M (Apache-2.0, offline) speaks each beat of script.json to public/vo/<id>.wav and writes
per-word timings to public/captions/<id>.json for karaoke captions. Cached: a beat is re-spoken only when its text,
voice or speed changes.   .venv/bin/python tools/tts.py [--voice af_heart] [--speed 1.0]"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
RATE = 24000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args()
    beats = json.loads((ROOT / "script.json").read_text())["beats"]
    vo, cap = ROOT / "public/vo", ROOT / "public/captions"
    vo.mkdir(parents=True, exist_ok=True)
    cap.mkdir(parents=True, exist_ok=True)
    pipe = None
    for b in beats:
        if not b.get("text"):
            continue
        tag = hashlib.sha256(f"{a.voice}|{a.speed}|{b['text']}".encode()).hexdigest()[:16]
        meta = cap / f"{b['id']}.json"
        if meta.exists() and json.loads(meta.read_text()).get("tag") == tag:
            continue
        if pipe is None:
            from kokoro import KPipeline

            pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
        audio, words, t0 = [], [], 0.0
        for r in pipe(b.get("say", b["text"]), voice=a.voice, speed=a.speed):
            chunk = r.audio.numpy()
            for t in r.tokens or []:
                if t.start_ts is not None and t.text.strip() and t.text not in ".,;:!?":
                    words.append({"text": t.text, "startMs": round((t0 + t.start_ts) * 1000),
                                  "endMs": round((t0 + (t.end_ts or t.start_ts)) * 1000)})
            audio.append(chunk)
            t0 += len(chunk) / RATE
        wav = np.concatenate(audio)
        sf.write(vo / f"{b['id']}.wav", wav, RATE)
        meta.write_text(json.dumps({"tag": tag, "seconds": round(len(wav) / RATE, 3), "words": words}, indent=1))
        print(f"{b['id']}: {len(wav) / RATE:.1f}s")


if __name__ == "__main__":
    main()
