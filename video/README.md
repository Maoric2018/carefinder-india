# Demo video (2:27)

The submission video, built from code: [Remotion](https://www.remotion.dev/) (React) for the scenes and app walkthroughs,
[Manim](https://www.manim.community/) for the math animations, and ElevenLabs for the voiceover. Rendered files are not in
the repo; the commands below rebuild them.

| Path | What |
|---|---|
| `voiceover.json` | The script: one entry per scene, with ElevenLabs v4 audio tags such as `[fast-paced]` |
| `tts.py` | Generates `public/audio/<scene>.mp3` and the word timings in `src/timing.json` (captions and cues use them) |
| `manim/method_scenes.py` | The four method animations (`ModelScene`, `OddsScene`, `ChecksScene`, `AccessScene`) |
| `manim/params.json` | Numbers shown in the animations, read from the fitted model in the live app |
| `manim/beats.json` | When each animation step starts, matched to the voiceover's word timings |
| `src/` | Remotion scenes: `scenes1.tsx` (hook, data), `demo.tsx` (app walkthroughs, planner), `method.tsx` (Manim clips), `scenes3.tsx` (close) |
| `public/` | Captures of the live app (`demo2/`, `plan2/`, `v5/`), generated stills (`img/`), voiceover and music (`audio/`) |
| `stills.mjs` | Renders a few preview frames: `node stills.mjs <outDir> <frame> [frame...]` |

## Rebuild

```bash
npm install
```

Voiceover (only if the script changes). The key is read from the environment, never stored. Scenes are sped up with a
pitch-preserving `atempo` after synthesis:

```bash
ELEVEN_API_KEY=... ELEVEN_ATEMPO=1.75 ELEVEN_ATEMPO_MAP='{"s1_hook":1.55,"s2_data":1.77,"s3_demo":1.85,"s4_results":1.73,"s5_pune":1.81,"s6_model":1.85,"s7_odds":1.85,"s8_checks":1.71,"s9_access":1.65,"s10_plan":1.81,"s11_close":1.6}' python3 tts.py
```

Math animations (rendered into `public/manim/`, which the Remotion scenes play):

```bash
cd manim && uv run --python 3.12 --with manim manim -qh --fps 30 -r 1920,1080 method_scenes.py ModelScene OddsScene ChecksScene AccessScene
mkdir -p ../public/manim && cp media/videos/method_scenes/1080p30/*Scene.mp4 ../public/manim/ && cd ..
```

Video, then loudness-normalise to −14 LUFS (two-pass `loudnorm` in ffmpeg):

```bash
npx remotion render src/index.ts CareFinder out/carefinder_raw.mp4 --codec h264 --crf 18
```

If Remotion reports "No available ports found" or Chrome cannot reach `localhost`, the machine's IPv6 loopback is
unreachable: preload a small script with `NODE_OPTIONS=--require` that filters IPv6 out of `os.networkInterfaces()` and
adds `--host-resolver-rules=MAP localhost 127.0.0.1` to the Chrome arguments.
