"""Hugging Face Spaces entry point (Gradio SDK auto-detects this file)."""
from wordwave.webui import build_demo

demo = build_demo()
demo.launch()
