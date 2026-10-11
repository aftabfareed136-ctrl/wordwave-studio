# 🌊 WordWave Studio

**Script → word-by-word kinetic typography video.** Write a script, pick a look, get a finished vertical video with an AI voiceover where every word lands exactly on the beat — the way big motion-design tools do it, from your terminal.

No After Effects. No Premiere. No timeline scrubbing. Just:

```bash
wordwave render my-script.txt -o video.mp4 --background cyberpunk --animator pop
```

## What it does

1. **Parses** your plain-text script into scenes (one kinetic card per sentence).
2. **Speaks** it with a neural AI voice and captures *word-level timestamps* — free forced alignment, so animation is sample-accurate to the voice.
3. **Composites** an After-Effects-style composition: animated background look + kinetic text layer with per-word keyframed animation + progress bar.
4. **Encodes** to MP4 (H.264) with the voiceover muxed in.

## AE-style engine (not a template stamper)

| After Effects concept | WordWave equivalent |
|---|---|
| Composition | `Composition(w, h, fps)` — ordered layers, back to front |
| Property keyframes + Easy Ease | `Keyframe(t, value, ease=...)` — 12 easings incl. back/elastic/bounce/spring overshoot |
| Text animators | 7 animator presets: `pop` `rise` `drop` `elastic` `swing` `karaoke` `typewriter` |
| Looks / adjustment layers | 4 procedural animated backgrounds: `cyberpunk` `neon` `ember` `minimal` |
| Per-character 3D | per-word scale/position/rotation/glow/pill-highlight, staggered to the voice |

## Quickstart

```bash
pip install edge-tts Pillow numpy
git clone <this-repo> && cd wordwave-studio

# list voices & styles
python -m wordwave.cli voices --locale ur-PK     # Urdu voices
python -m wordwave.cli styles

# render the demo (~25s, 9:16)
python -m wordwave.cli demo -o demo.mp4

# render your own script
python -m wordwave.cli render script.txt -o out.mp4 \
  --voice en-US-AriaNeural --background neon --animator karaoke --ar 16:9
```

Needs `ffmpeg` on PATH. First render downloads the voice model data via edge-tts; re-renders are cached (`~/.cache/wordwave`).

## Script format

```text
# comments and blank lines are ignored

## TITLE CARD            <- big centered title scene

Every sentence becomes one scene. !Money loves !speed.
[pause 0.8]             <- beat of silence in the voiceover
```

- `!word` → keyword, always rendered in the accent colour
- `##` → title-card scene
- `[pause X]` → X seconds of silence

## Python API

```python
from wordwave.renderer import render
render("script.txt", "out.mp4", voice="ur-PK-AsadNeural",
       background="cyberpunk", animator="pop", w=1080, h=1920, fps=30)
```

## Roadmap

- [ ] SRT/VTT export of word timings (for Premiere/AE import)
- [ ] Image/video background layers + face-cam PiP layer
- [ ] Web UI (FastAPI + preview player)
- [ ] Multi-language auto voice pick

## License

MIT — do whatever you want with it.
