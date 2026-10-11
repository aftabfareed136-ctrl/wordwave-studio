"""WordWave Studio CLI."""
from __future__ import annotations

import argparse
import sys

from .presets import BACKGROUNDS
from .timeline import TEXT_ANIMATORS


def _ar(value: str) -> tuple[int, int]:
    presets = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
    if value in presets:
        return presets[value]
    w, h = value.lower().split("x")
    return int(w), int(h)


def cmd_render(args):
    from .renderer import render
    w, h = _ar(args.ar)
    render(args.script, args.out, voice=args.voice, background=args.background,
           animator=args.animator, w=w, h=h, fps=args.fps)


def cmd_voices(args):
    from .tts import list_voices
    voices = list_voices(args.locale)
    for v in sorted(voices, key=lambda v: v["ShortName"]):
        print(f'{v["ShortName"]:32s} {v["Locale"]:8s} {v["Gender"]:6s} {v["FriendlyName"]}')


def cmd_animators(_args):
    print("Text animators (AE-style presets):")
    for name in sorted(TEXT_ANIMATORS):
        print(f"  {name}")
    print("\nBackground looks:")
    for name in sorted(BACKGROUNDS):
        print(f"  {name}")


def cmd_demo(args):
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    demo = os.path.join(here, "..", "examples", "demo-script.txt")
    from .renderer import render
    w, h = _ar(args.ar)
    render(demo, args.out, voice=args.voice, background=args.background,
           animator=args.animator, w=w, h=h, fps=args.fps)


def main(argv=None):
    p = argparse.ArgumentParser(prog="wordwave",
                                description="Script → word-by-word kinetic typography video")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Render a script file to mp4")
    r.add_argument("script", help="Path to .txt script (see examples/demo-script.txt)")
    r.add_argument("-o", "--out", default="wordwave-out.mp4")
    r.add_argument("--voice", default="en-US-AriaNeural", help="edge-tts voice id")
    r.add_argument("--background", default="cyberpunk", choices=sorted(BACKGROUNDS))
    r.add_argument("--animator", default="pop", choices=sorted(TEXT_ANIMATORS))
    r.add_argument("--ar", default="9:16", help="9:16 | 16:9 | 1:1 | WxH")
    r.add_argument("--fps", type=int, default=30)
    r.set_defaults(func=cmd_render)

    d = sub.add_parser("demo", help="Render the bundled demo script")
    d.add_argument("-o", "--out", default="wordwave-demo.mp4")
    d.add_argument("--voice", default="en-US-AriaNeural")
    d.add_argument("--background", default="cyberpunk", choices=sorted(BACKGROUNDS))
    d.add_argument("--animator", default="pop", choices=sorted(TEXT_ANIMATORS))
    d.add_argument("--ar", default="9:16")
    d.add_argument("--fps", type=int, default=30)
    d.set_defaults(func=cmd_demo)

    v = sub.add_parser("voices", help="List available TTS voices")
    v.add_argument("--locale", default=None, help="e.g. en, ur-PK")
    v.set_defaults(func=cmd_voices)

    l = sub.add_parser("styles", help="List animators and background looks")
    l.set_defaults(func=cmd_animators)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
