"""Render pipeline: script -> voiceover -> AE-style comp -> mp4.

Frames are composited with PIL (full keyframe control, like AE's renderer)
and streamed as raw video into ffmpeg; the voiceover is muxed at the end.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from . import tts as tts_mod
from .presets import BACKGROUNDS, BackgroundLayer
from .script_parser import parse_file, tts_text
from .timeline import Composition, KineticTextLayer, ProgressBarLayer, ScoredWord, SceneTake
from .tts import align_to_scenes


def build_composition(script_path: str, voice: str, background: str, animator: str,
                      w: int, h: int, fps: int,
                      hold_out: float = 0.8, tail: float = 1.0):
    scenes = parse_file(script_path)
    if not scenes:
        raise ValueError("No scenes parsed from script.")
    print(f"  scenes: {len(scenes)}  |  voice: {voice}", flush=True)

    print("  synthesizing voiceover + word timestamps ...", flush=True)
    audio_path, timed = tts_mod.synthesize(tts_text(scenes), voice)
    per_scene = align_to_scenes(scenes, timed)

    takes: list[SceneTake] = []
    cursor = 0.0
    for scene, words in zip(scenes, per_scene):
        if not words:
            continue
        scored = [ScoredWord(text=s.text, start=s.start, end=s.end, keyword=w.keyword)
                  for s, w in zip(words, scene.words)]
        start = max(cursor, scored[0].start - 0.35)
        end = scored[-1].end + hold_out + scene.pause_after
        takes.append(SceneTake(words=scored, title=scene.title, start=start, end=end))
        cursor = end

    duration = takes[-1].end + tail
    accent = BACKGROUNDS[background]["accent"]
    accent2 = BACKGROUNDS[background]["accent2"]

    comp = Composition(w, h, fps, duration)
    comp.add(BackgroundLayer(background))
    comp.add(KineticTextLayer(takes, animator=animator, accent=accent, accent2=accent2))
    comp.add(ProgressBarLayer(duration, accent=accent))
    return comp, audio_path, duration


def render_frames(comp: Composition, out_path: str, crf: int = 18, preset: str = "veryfast"):
    n = int(comp.duration * comp.fps)
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{comp.w}x{comp.h}",
           "-r", str(comp.fps), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", str(crf), "-preset", preset, out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n):
            t = i / comp.fps
            frame = comp.frame(t)
            proc.stdin.write(frame.tobytes())
            if i % max(1, n // 20) == 0:
                print(f"\r  rendering: {100 * i / n:5.1f}%  ({i}/{n} frames)", end="", flush=True)
    finally:
        proc.stdin.close()
        proc.wait()
    print(f"\r  rendering: 100.0%  ({n}/{n} frames)", flush=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg frame encode failed")


def mux_audio(video_path: str, audio_path: str, out_path: str, duration: float):
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-i", video_path, "-i", audio_path,
           "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
           "-t", f"{duration:.2f}", "-shortest", out_path]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg audio mux failed")


def render(script_path: str, out_path: str, voice: str = "en-US-AriaNeural",
           background: str = "cyberpunk", animator: str = "pop",
           w: int = 1080, h: int = 1920, fps: int = 30) -> str:
    print(f"WordWave Studio — {os.path.basename(script_path)} -> {out_path}", flush=True)
    print(f"  look: {background}  |  animator: {animator}  |  {w}x{h}@{fps}", flush=True)
    comp, audio_path, duration = build_composition(
        script_path, voice, background, animator, w, h, fps)
    print(f"  duration: {duration:.1f}s", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        silent = os.path.join(tmp, "silent.mp4")
        render_frames(comp, silent)
        mux_audio(silent, audio_path, out_path, duration)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"  done: {out_path} ({size_mb:.1f} MB)", flush=True)
    return out_path
