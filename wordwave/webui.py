"""WordWave Studio web UI (Gradio).

Run locally or in GitHub Codespaces:
    python -m wordwave.webui
Then open the URL it prints (in Codespaces, use the forwarded port 7860).
"""
from __future__ import annotations

import os
import tempfile

import gradio as gr

from .presets import BACKGROUNDS
from .renderer import render
from .timeline import TEXT_ANIMATORS

VOICES = [
    ("English (US) - Aria, female", "en-US-AriaNeural"),
    ("English (US) - Guy, male", "en-US-GuyNeural"),
    ("English (UK) - Sonia, female", "en-GB-SoniaNeural"),
    ("Urdu (Pakistan) - Asad, male", "ur-PK-AsadNeural"),
    ("Urdu (Pakistan) - Ayesha, female", "ur-PK-AyeshaNeural"),
]

QUALITIES = {
    "720p - fast (720x1280)": (720, 1280),
    "1080p - best (1080x1920)": (1080, 1920),
}

DEMO_SCRIPT = """## WORD BY WORD

Every great video you have ever watched was built one !word at a time.

[pause 0.6] After Effects animators call this kinetic typography.

WordWave reads your !script, speaks it with an AI voice, and lands every single word exactly on the !beat.

Pop, rise, karaoke, typewriter — pick an animator, pick a look, and !render.
"""

HELP = """**Script tips:** every sentence becomes one scene · `!word` = keyword highlight ·
`## Title` = title card · `[pause 0.8]` = beat of silence · `#` = comment"""


def make_video(script: str, voice: str, background: str, animator: str,
               quality: str, progress=gr.Progress(track_tqdm=False)):
    if not script or not script.strip():
        raise gr.Error("Please paste a script first.")
    w, h = QUALITIES[quality]
    tmpdir = tempfile.mkdtemp(prefix="wordwave-")
    script_path = os.path.join(tmpdir, "script.txt")
    out_path = os.path.join(tmpdir, "wordwave.mp4")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    def cb(frac: float):
        progress(frac, desc=f"Rendering {int(frac * 100)}%")

    progress(0, desc="Synthesizing voiceover...")
    render(script_path, out_path, voice=voice, background=background,
           animator=animator, w=w, h=h, fps=30, progress_cb=cb)
    progress(1.0, desc="Done!")
    return out_path


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="WordWave Studio") as demo:
        gr.Markdown("# 🌊 WordWave Studio\n**Script → word-by-word kinetic typography video.** Paste a script, pick a look, hit Render.")
        with gr.Row():
            script = gr.Textbox(label="Script", lines=12, value=DEMO_SCRIPT,
                                placeholder="Type or paste your script here...")
        gr.Markdown(HELP)
        with gr.Row():
            voice = gr.Dropdown([v[1] for v in VOICES], value=VOICES[0][1], label="Voice")
            background = gr.Dropdown(sorted(BACKGROUNDS), value="cyberpunk", label="Look")
            animator = gr.Dropdown(sorted(TEXT_ANIMATORS), value="pop", label="Animator")
            quality = gr.Dropdown(list(QUALITIES), value=list(QUALITIES)[0], label="Quality")
        render_btn = gr.Button("🎬 Render video", variant="primary")
        video = gr.Video(label="Result", interactive=False)
        render_btn.click(make_video,
                         inputs=[script, voice, background, animator, quality],
                         outputs=video)
        gr.Examples([[DEMO_SCRIPT]], inputs=script, label="Try the demo script")
    return demo


def main():
    demo = build_demo()
    demo.launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
