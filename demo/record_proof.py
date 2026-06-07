"""Record the proof-of-deployment GIF for Qwen Cloud Hackathon.

Records the proof_terminal.html with Playwright, then converts WebM → GIF
with ffmpeg using an optimized palette for small file size.
"""

import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_DIR = Path("/opt/data/webui/minions/.minions-data/workspace/perseus-qwen-memory")
HTML_PATH = PROJECT_DIR / "demo" / "proof_terminal.html"
OUTPUT_DIR = PROJECT_DIR / "demo" / "proof_output"
WEBM_PATH = OUTPUT_DIR / "proof.webm"
GIF_PATH = PROJECT_DIR / "demo" / "proof_deployment.gif"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
for f in OUTPUT_DIR.glob("*"):
    f.unlink()

# Total animation: ~60s of lines, ~13s scene delays = ~73s
# GIF should be ~15-20s — record the whole thing but trim to highlights
DURATION = 75

print(f"Recording: {HTML_PATH}")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1080, "height": 600},
        record_video_dir=str(OUTPUT_DIR),
        record_video_size={"width": 1080, "height": 600},
    )
    page = context.new_page()
    page.goto(f"file://{HTML_PATH}", wait_until="networkidle")
    print(f"Recording for {DURATION}s...")
    time.sleep(DURATION)
    context.close()
    browser.close()

# Find WebM
webm_files = list(OUTPUT_DIR.glob("*.webm"))
if not webm_files:
    print("ERROR: No WebM found!")
    exit(1)
webm = webm_files[0]
print(f"WebM: {webm.stat().st_size / 1024:.0f} KB")

# Trim to first 50s (API call + response + verification) and convert to GIF
# Use palette optimization for small file size
print("Converting to optimized GIF...")
subprocess.run([
    "ffmpeg", "-y",
    "-i", str(webm),
    "-t", "50",  # trim to 50s
    "-vf", "fps=10,scale=1080:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
    "-loop", "0",
    str(GIF_PATH),
], capture_output=True, timeout=60, check=True)

size_kb = GIF_PATH.stat().st_size / 1024
print(f"GIF: {GIF_PATH} ({size_kb:.0f} KB)")

if size_kb > 5000:
    print("⚠ GIF > 5MB — GitHub might reject. Re-encoding at lower FPS...")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(webm),
        "-t", "50",
        "-vf", "fps=6,scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
        "-loop", "0",
        str(GIF_PATH),
    ], capture_output=True, timeout=60, check=True)
    size_kb = GIF_PATH.stat().st_size / 1024
    print(f"Re-encoded GIF: {size_kb:.0f} KB")

print(f"\n✅ Proof GIF ready: {GIF_PATH}")
