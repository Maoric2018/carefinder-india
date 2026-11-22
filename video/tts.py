"""Generate one MP3 per scene with ElevenLabs (Eleven v4, audio tags), plus word timings for captions and cues.

The API key comes from ELEVEN_API_KEY (never stored on disk). Writes public/audio/<id>.mp3 and
src/timing.json ({id: {duration, words: [{w, s, e}]}}). Bracketed audio tags like [excited] steer delivery
and are dropped from the word timings.

Usage: ELEVEN_API_KEY=... python3 tts.py [scene ids...]   (env: ELEVEN_MODEL, ELEVEN_SPEED, ELEVEN_STABILITY)
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
VOICE = os.environ.get("ELEVEN_VOICE", "bwAU2gC0ssIxDyMcOITU")
MODEL = os.environ.get("ELEVEN_MODEL", "eleven_v4")
SPEED = float(os.environ.get("ELEVEN_SPEED", "1.1"))
STABILITY = float(os.environ.get("ELEVEN_STABILITY", "0.4"))
KEY = os.environ["ELEVEN_API_KEY"]
only = set(sys.argv[1:])

scenes = json.loads((HERE / "voiceover.json").read_text())
timing_path = HERE / "src" / "timing.json"
timing = json.loads(timing_path.read_text()) if timing_path.exists() else {}
TAG = re.compile(r"\[[^\]]*\]\s*")


def words_from(alignment):
    """Spoken words with start/end times; characters inside [tags] are skipped."""
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    words, cur, s, e, in_tag = [], "", None, None, False

    def flush():
        nonlocal cur, s
        if cur:
            words.append({"w": cur, "s": round(s, 3), "e": round(e, 3)})
        cur, s = "", None

    for ch, cs, ce in zip(chars, starts, ends):
        if ch == "[":
            flush()
            in_tag = True
            continue
        if in_tag:
            in_tag = ch != "]"
            continue
        if ch.isspace():
            flush()
            continue
        if s is None:
            s = cs
        cur += ch
        e = ce
    flush()
    return words


def synth(body):
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/with-timestamps?output_format=mp3_44100_128",
        data=json.dumps(body).encode(), method="POST",
        headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


ATEMPO = float(os.environ.get("ELEVEN_ATEMPO", "1.0"))  # pitch-preserving speed-up applied after synthesis
ATEMPO_MAP = json.loads(os.environ.get("ELEVEN_ATEMPO_MAP", "{}"))  # per-scene overrides, e.g. {"s1_hook": 1.4}
RETIME = os.environ.get("RETIME_ONLY") == "1"  # re-apply ATEMPO to saved raw takes without calling the API
raw_dir = HERE / "public" / "audio" / "raw"
raw_dir.mkdir(parents=True, exist_ok=True)
raw_timing_path = HERE / "src" / "timing_raw.json"
raw_timing = json.loads(raw_timing_path.read_text()) if raw_timing_path.exists() else {}

for i, sc in enumerate(scenes):
    out = HERE / "public" / "audio" / f"{sc['id']}.mp3"
    raw = raw_dir / f"{sc['id']}.mp3"
    if not RETIME and (not only or sc["id"] in only):
        body = {
            "text": sc["text"],
            "model_id": MODEL,
            "voice_settings": {"stability": STABILITY, "similarity_boost": 0.8, "speed": SPEED},
            "previous_text": TAG.sub("", scenes[i - 1]["text"]) if i > 0 else None,
            "next_text": TAG.sub("", scenes[i + 1]["text"]) if i + 1 < len(scenes) else None,
        }
        try:
            data = synth(body)
        except urllib.error.HTTPError as err:  # some models reject request stitching
            print(sc["id"], "retrying without context:", err.code, err.read()[:200])
            body.pop("previous_text")
            body.pop("next_text")
            data = synth(body)
        raw.write_bytes(base64.b64decode(data["audio_base64"]))
        raw_timing[sc["id"]] = words_from(data["alignment"])
        raw_timing_path.write_text(json.dumps(raw_timing, indent=1))
    if RETIME or not only or sc["id"] in only:
        at = float(ATEMPO_MAP.get(sc["id"], ATEMPO))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-filter:a", f"atempo={at}",
                        "-b:a", "160k", str(out)], check=True)
        timing[sc["id"]] = {"words": [{"w": w["w"], "s": round(w["s"] / at, 3), "e": round(w["e"] / at, 3)}
                                      for w in raw_timing[sc["id"]]]}
    d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                        "-of", "csv=p=0", str(out)]).decode().strip())
    timing.setdefault(sc["id"], {})["duration"] = round(d, 3)
    n = len(timing[sc["id"]].get("words", []))
    print(f"{sc['id']:12s} {d:6.2f}s  {n} words  {n / d:.2f} w/s")

timing = {sc["id"]: timing[sc["id"]] for sc in scenes}
timing_path.parent.mkdir(exist_ok=True)
timing_path.write_text(json.dumps(timing, indent=1))
print(f"total {sum(v['duration'] for v in timing.values()):.1f}s")
