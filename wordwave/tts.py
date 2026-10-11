"""Voiceover synthesis with word-level timestamps (forced alignment for free).

Uses the edge-tts service's word-boundary events, so every spoken word gets
an exact (start, end) — the backbone of word-by-word animation. The service
is reached through `edge_ws`, a minimal websocket client that tolerates the
sandbox egress proxy (which rewrites the WS handshake's Connection header
and breaks strict clients like aiohttp). Results are cached under
~/.cache/wordwave so re-renders are instant.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

from . import edge_ws

CACHE_DIR = os.path.expanduser("~/.cache/wordwave")


@dataclass
class TimedWord:
    text: str
    start: float  # seconds
    end: float    # seconds


def synthesize(text: str, voice: str = "en-US-AriaNeural") -> tuple[str, list[TimedWord]]:
    """Returns (mp3_path, timed_words). Cached by sha1(voice + text)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1(f"{voice}::{text}".encode("utf-8")).hexdigest()[:16]
    mp3_path = os.path.join(CACHE_DIR, f"{key}.mp3")
    json_path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(mp3_path) and os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        return mp3_path, [TimedWord(**w) for w in data]
    raw = edge_ws.synthesize(text, voice, mp3_path)
    words = [TimedWord(text=w["text"], start=w["start"], end=w["end"]) for w in raw]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([w.__dict__ for w in words], f)
    return mp3_path, words


def list_voices(locale_prefix: str | None = None) -> list[dict]:
    return edge_ws.list_voices(locale_prefix)


def align_to_scenes(scenes, timed_words: list[TimedWord]) -> list[list[TimedWord]]:
    """Consume boundary words in order, one scene's worth at a time.

    edge-tts sometimes splits/merges tokens (\"don't\" -> \"don\", \"'t\"),
    so we match greedily by count with a punctuation-insensitive fallback.
    """
    import re

    def norm(s: str) -> str:
        return re.sub(r"[^\w]", "", s).lower()

    per_scene: list[list[TimedWord]] = []
    i = 0
    n = len(timed_words)
    for scene in scenes:
        want = len(scene.words)
        got: list[TimedWord] = []
        for w in scene.words:
            # skip punctuation-only boundaries (e.g. from pause commas)
            while i < n and not norm(timed_words[i].text):
                i += 1
            if i >= n:
                break
            tw = timed_words[i]
            # merge following fragments if they clearly belong to this token
            # (e.g. "don" + "'t" for "don't")
            merged = tw.text
            j = i
            while norm(merged) != norm(w.text) and j + 1 < n and len(norm(merged)) < len(norm(w.text)) + 3:
                j += 1
                merged += timed_words[j].text
            got.append(TimedWord(text=w.text, start=tw.start, end=timed_words[j].end))
            i = j + 1
        # if the TTS dropped words, pad with the last known timing
        while len(got) < want and got:
            last = got[-1]
            got.append(TimedWord(text=scene.words[len(got)].text, start=last.end, end=last.end + 0.25))
        per_scene.append(got)
    return per_scene
