"""Record the Perseus Qwen Memory Agent demo video.

Uses Playwright's built-in video recording to capture the terminal
simulation HTML, then converts WebM to MP4 with FFmpeg.

Total demo duration: ~170 seconds (~2:50)
"""

import time
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_DIR = Path("/opt/data/webui/minions/.minions-data/workspace/perseus-qwen-memory")
HTML_PATH = PROJECT_DIR / "demo" / "demo_terminal.html"
VIDEO_DIR = PROJECT_DIR / "demo" / "video_output"
OUTPUT_VIDEO = PROJECT_DIR / "demo" / "demo_video.mp4"

# Ensure video output directory exists
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# Clean previous recordings
for f in VIDEO_DIR.glob("*"):
    f.unlink()

# Total duration: the demo script runs ~50 lines, I'll wait 170 seconds
TOTAL_DURATION = 170

print(f"Recording demo from: {HTML_PATH}")
print(f"Duration: {TOTAL_DURATION}s")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        record_video_dir=str(VIDEO_DIR),
        record_video_size={"width": 1280, "height": 720},
    )
    page = context.new_page()
    page.goto(f"file://{HTML_PATH}", wait_until="networkidle")
    print("Page loaded, recording...")

    # Wait for the demo to fully play out
    time.sleep(TOTAL_DURATION)

    context.close()
    browser.close()
    print("Recording complete.")

# Find the WebM file
webm_files = list(VIDEO_DIR.glob("*.webm"))
if not webm_files:
    print("ERROR: No WebM file found!")
    exit(1)

webm_path = webm_files[0]
print(f"WebM: {webm_path} ({webm_path.stat().st_size / 1024:.0f} KB)")

# Convert to MP4
import subprocess
print("Converting to MP4...")
result = subprocess.run([
    "ffmpeg", "-y",
    "-i", str(webm_path),
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "23",
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    str(OUTPUT_VIDEO),
], capture_output=True, text=True, timeout=120)

if result.returncode != 0:
    print(f"FFmpeg error:\n{result.stderr[-500:]}")
    exit(1)

print(f"MP4: {OUTPUT_VIDEO} ({OUTPUT_VIDEO.stat().st_size / 1024:.0f} KB)")

# Extract frames for quality check
for ss, name in [(25, "f1"), (80, "f2"), (150, "f3")]:
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(OUTPUT_VIDEO),
        "-ss", str(ss),
        "-vframes", "1",
        str(PROJECT_DIR / "demo" / f"{name}.png"),
    ], capture_output=True, timeout=10)
    print(f"  Frame {name}: {ss}s")

print("\n✅ Demo video ready:", OUTPUT_VIDEO)
