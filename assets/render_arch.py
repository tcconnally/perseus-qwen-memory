"""Render architecture diagram HTML to PNG for Devpost submission."""
import time, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT = Path("/opt/data/webui/minions/.minions-data/workspace/perseus-qwen-memory")
HTML = PROJECT / "assets" / "architecture.html"
PNG = PROJECT / "assets" / "architecture.png"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    page.goto(f"file://{HTML}", wait_until="networkidle")
    time.sleep(2)
    page.screenshot(path=str(PNG), full_page=True)
    browser.close()

size_kb = PNG.stat().st_size / 1024
print(f"PNG: {PNG} ({size_kb:.0f} KB)")
