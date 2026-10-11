"""Parse a plain-text script into scenes of words.

Script markup (all optional):
    ## Title            -> title card scene (rendered big, centered)
    !word               -> keyword: always rendered in the accent colour
    [pause 0.8]         -> adds a beat of silence after the previous scene
    # comment           -> ignored (single #, not ##)
    blank line          -> scene break

Every sentence becomes one scene (one kinetic-typography card on screen).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
PAUSE_TAG = re.compile(r"\[pause\s+([\d.]+)\]")
TITLE_TAG = re.compile(r"^##\s*(.+)$")
COMMENT_TAG = re.compile(r"^#(?!#)")
TRAILING_PUNCT = ".,!?…;:…"


@dataclass
class Word:
    text: str
    keyword: bool = False


@dataclass
class Scene:
    words: list[Word] = field(default_factory=list)
    title: bool = False  # title card scene
    pause_after: float = 0.0  # extra silence after this scene (seconds)

    @property
    def plain_text(self) -> str:
        return " ".join(w.text for w in self.words)


def _clean_token(tok: str) -> tuple[str, bool]:
    keyword = tok.startswith("!") and len(tok) > 1
    text = tok[1:] if keyword else tok
    text = text.strip("\"'“”‘’()[]")
    if keyword:
        # "!focus." -> keyword "focus" (displayed without the trailing dot)
        text = text.rstrip(TRAILING_PUNCT)
    return text, keyword


def parse_script(text: str) -> list[Scene]:
    scenes: list[Scene] = []

    def add_pause(seconds: float):
        # a pause belongs to the gap *before* the upcoming scene, so it
        # extends the previous scene's hold (or the very first scene's lead)
        if scenes:
            scenes[-1].pause_after += seconds

    def flush_sentence(sentence: str, title: bool = False):
        sentence = sentence.strip()
        if not sentence:
            return
        for m in PAUSE_TAG.finditer(sentence):
            add_pause(float(m.group(1)))
        sentence = PAUSE_TAG.sub(" ", sentence)
        words: list[Word] = []
        for tok in sentence.split():
            clean, kw = _clean_token(tok)
            if clean:
                words.append(Word(clean, kw))
        if words:
            scenes.append(Scene(words=words, title=title))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or COMMENT_TAG.match(line):
            continue
        tm = TITLE_TAG.match(line)
        if tm:
            flush_sentence(tm.group(1), title=True)
            continue
        for sentence in SENTENCE_END.split(line):
            flush_sentence(sentence)

    return scenes


def parse_file(path: str) -> list[Scene]:
    with open(path, encoding="utf-8") as f:
        return parse_script(f.read())


def tts_text(scenes: list[Scene]) -> str:
    """Single string fed to the voiceover engine.

    Pauses become commas (natural TTS breath); the *visual* hold for the
    pause is handled by the scene timing, so the boundary-word count stays
    exactly aligned with the script words.
    """
    chunks = []
    for s in scenes:
        chunks.append(s.plain_text)
        if s.pause_after > 0:
            chunks.append(", " * max(1, int(round(s.pause_after / 0.4))))
    return " ".join(chunks)
