#!/usr/bin/env python3
"""
Runtime CPU measurement for HTML5 banners using Playwright + CDP.

Measures Chrome TaskDuration over a 30-second window to detect
banners that would trigger Chrome's Heavy Ad Intervention (>15s CPU per 30s).
"""

import os
import re
import sys
import zipfile
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def _find_primary_html(zip_path):
    """Find the primary HTML file inside a ZIP (same logic as scan_banners)."""
    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile:
        return None

    infos = [i for i in zf.infolist() if not i.is_dir() and not i.filename.startswith("__MACOSX")]
    filenames = [i.filename for i in infos]
    zf.close()

    root_htmls = [f for f in filenames if "/" not in f and os.path.splitext(f)[1].lower() in (".html", ".htm")]
    if root_htmls:
        return next((c for c in root_htmls if c.lower() == "index.html"), root_htmls[0])

    all_htmls = [f for f in filenames if os.path.splitext(f)[1].lower() in (".html", ".htm")]
    if all_htmls:
        return all_htmls[0]

    return None


class _QuietHandler(SimpleHTTPRequestHandler):
    """HTTP handler that suppresses log output."""

    def log_message(self, format, *args):
        pass


def _serve_directory(directory):
    """Start a threaded HTTP server serving the given directory on a random port."""
    class Handler(_QuietHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def measure_banner_cpu(zip_path, duration=30):
    """
    Measure CPU time of a banner over a given duration (seconds).

    Returns dict with:
        ok: bool - whether measurement succeeded
        cpu_seconds: float - TaskDuration delta (only if ok)
        exceeds: bool - whether cpu_seconds > 15 (only if ok)
        error: str - error message (only if not ok)
    """
    primary_html = _find_primary_html(zip_path)
    if not primary_html:
        return {"ok": False, "error": "No HTML file found in ZIP"}

    server = None
    browser = None
    tmpdir = None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "Playwright not installed"}

    try:
        # Extract ZIP to temp directory
        tmpdir = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir.name)

        # Start local HTTP server
        server, port = _serve_directory(tmpdir.name)
        url = f"http://127.0.0.1:{port}/{primary_html}"

        # Detect ad size from HTML meta tag
        html_path = os.path.join(tmpdir.name, primary_html)
        width, height = 300, 250  # default
        try:
            with open(html_path, "r", encoding="utf-8", errors="replace") as f:
                html_content = f.read()
            ad_m = re.search(
                r'<meta\s+name=["\']ad\.size["\']\s+content=["\']width=(\d+),\s*height=(\d+)["\']',
                html_content, re.I
            )
            if ad_m:
                width, height = int(ad_m.group(1)), int(ad_m.group(2))
        except Exception:
            pass

        # Launch Playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()

        # Create CDP session and enable Performance
        cdp = context.new_cdp_session(page)
        cdp.send("Performance.enable")

        # Read initial TaskDuration
        metrics_before = cdp.send("Performance.getMetrics")
        td_before = 0.0
        for m in metrics_before.get("metrics", []):
            if m["name"] == "TaskDuration":
                td_before = m["value"]
                break

        # Navigate and wait, sampling JSHeapUsedSize periodically
        page.goto(url, wait_until="load", timeout=15000)

        peak_heap = 0
        sample_interval = 2000  # ms
        elapsed = 0
        while elapsed < duration * 1000:
            wait_ms = min(sample_interval, duration * 1000 - elapsed)
            page.wait_for_timeout(wait_ms)
            elapsed += wait_ms
            try:
                sample = cdp.send("Performance.getMetrics")
                for m in sample.get("metrics", []):
                    if m["name"] == "JSHeapUsedSize":
                        peak_heap = max(peak_heap, m["value"])
                        break
            except Exception:
                pass

        # Read final TaskDuration
        metrics_after = cdp.send("Performance.getMetrics")
        td_after = 0.0
        for m in metrics_after.get("metrics", []):
            if m["name"] == "TaskDuration":
                td_after = m["value"]
            elif m["name"] == "JSHeapUsedSize":
                peak_heap = max(peak_heap, m["value"])

        cpu_seconds = round(td_after - td_before, 2)
        peak_heap_mb = round(peak_heap / (1024 * 1024), 2)
        return {
            "ok": True,
            "cpu_seconds": cpu_seconds,
            "exceeds": cpu_seconds > 15,
            "peak_heap_mb": peak_heap_mb,
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}

    finally:
        # Guaranteed cleanup
        if browser:
            try:
                browser.close()
                pw.stop()
            except Exception:
                pass
        if server:
            try:
                server.shutdown()
            except Exception:
                pass
        if tmpdir:
            try:
                tmpdir.cleanup()
            except Exception:
                pass
