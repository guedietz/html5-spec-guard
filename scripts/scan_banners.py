#!/usr/bin/env python3
"""
HTML5 Spec Guard - Banner Scanner

Scans ZIP files against CM360/DV360/TTD/Adform specs and outputs JSON results.
Can optionally generate PDF report directly.

Usage:
    python scan_banners.py --scan-dir scan/ --platforms cm360,dv360
    python scan_banners.py --scan-dir scan/ --platforms ttd --pdf output/report.pdf
    python scan_banners.py --scan-dir scan/ --platforms adform --pdf output/report.pdf
    python scan_banners.py --scan-dir scan/ --platforms all --pdf output/report.pdf
"""

import zipfile
import os
import re
import json
import sys
import argparse
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

@dataclass
class CheckResult:
    id: str
    status: str  # "PASS" | "FAIL" | "WARNING" | "INFO"
    message: str
    suggestion: Optional[str] = None


@dataclass
class BannerResult:
    filename: str
    platform: str
    metadata: dict
    checks: list[CheckResult] = field(default_factory=list)


@dataclass
class ScanResult:
    title: str
    scan_timestamp: str
    banners: list[BannerResult] = field(default_factory=list)


RUNTIME_AVAILABLE = False
try:
    from runtime_checks import measure_banner_cpu
    RUNTIME_AVAILABLE = True
except ImportError:
    pass

CM360_ALLOWED = {
    ".html", ".htm", ".js", ".css", ".jpg", ".jpeg", ".gif", ".png",
    ".json", ".xml", ".svg", ".eot", ".otf", ".ttf", ".woff", ".woff2",
}
DV360_ALLOWED = {
    ".html", ".htm", ".css", ".js", ".jpg", ".jpeg", ".gif", ".png",
    ".svg", ".dfont", ".eot", ".otf", ".tte", ".ttf", ".woff", ".woff2",
}
TTD_ALLOWED = {
    ".html", ".htm", ".js", ".css", ".mp4",
    ".jpg", ".jpeg", ".gif", ".png", ".svg",
}
ADFORM_ALLOWED = {
    ".html", ".htm", ".js", ".css", ".jpg", ".jpeg", ".gif", ".png",
    ".svg", ".json", ".xml", ".eot", ".otf", ".ttf", ".woff", ".woff2",
    ".mp4", ".webm",
}
AMAZONDSP_ALLOWED = {
    ".html", ".htm", ".js", ".css", ".jpg", ".jpeg", ".png", ".gif",
    ".woff", ".eot", ".json",
}
TEXT_EXTS = {".html", ".htm", ".js", ".css", ".json", ".xml", ".svg"}

MOBILE_SIZES = {"320x50", "320x100", "300x50", "300x250"}
HEAVY_AD_THRESHOLD = 4_194_304  # 4 MB

BUNDLED_LIBS = {
    "GSAP": {
        "filenames": {"gsap.min.js", "gsap.js", "tweenmax.min.js", "tweenmax.js",
                      "tweenlite.min.js", "tweenlite.js"},
        "signatures": [r"\bgsap\.\w+", r"\bTweenMax\b", r"\bTweenLite\b", r"\bTimelineMax\b"],
        "cdn": "https://cdnjs.cloudflare.com/ajax/libs/gsap/",
    },
    "jQuery": {
        "filenames": {"jquery.min.js", "jquery.js", "jquery.slim.min.js"},
        "signatures": [r"jQuery\s+v\d", r"\.fn\.jquery\s*="],
        "cdn": "https://code.jquery.com/",
    },
    "anime.js": {
        "filenames": {"anime.min.js", "anime.js"},
        "signatures": [r"animejs\.com", r"anime\(\s*\{"],
        "cdn": "https://cdnjs.cloudflare.com/ajax/libs/animejs/",
    },
    "CreateJS": {
        "filenames": {"createjs.min.js", "createjs.js", "easeljs.min.js", "tweenjs.min.js"},
        "signatures": [r"\bcreatejs\b", r"this\.createjs\s*="],
        "cdn": "https://code.createjs.com/",
    },
}

ALLOWED_DOMAINS = {
    "google.com", "doubleclick.net", "2mdn.net",
    "googlesyndication.com", "googletagmanager.com",
    "googletagservices.com", "google-analytics.com",
    "googleapis.com", "gstatic.com",
    "cdnjs.cloudflare.com", "cdn.jsdelivr.net",
    "www.w3.org",
    "s1.adform.net", "adform.net", "adform.com",
    "adkit-advertising.amazon",
}

JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini", ".gitkeep"}


def estimate_initial_load(primary_html, infos):
    """Estimate initial load payload by parsing <head> and pre-polite <body> references."""
    if not primary_html:
        return 0, []

    # Build lookup from basename/path to file_size
    size_lookup = {}
    for info in infos:
        basename = os.path.basename(info.filename).lower()
        size_lookup[basename] = info.file_size
        size_lookup[info.filename.lower()] = info.file_size

    # Extract <head> content
    head_match = re.search(r"<head[^>]*>(.*?)</head>", primary_html, re.I | re.S)
    head_content = head_match.group(1) if head_match else ""

    # Extract <body> content up to first polite-load pattern
    body_match = re.search(r"<body[^>]*>(.*)", primary_html, re.I | re.S)
    body_content = body_match.group(1) if body_match else ""

    polite_patterns = [
        r'window\.addEventListener\s*\(\s*["\']load["\']',
        r'document\.addEventListener\s*\(\s*["\']DOMContentLoaded["\']',
        r'Enabler\.isPageLoaded\s*\(',
        r'Enabler\.isInitialized\s*\(',
    ]
    earliest_pos = len(body_content)
    for pat in polite_patterns:
        m = re.search(pat, body_content)
        if m and m.start() < earliest_pos:
            earliest_pos = m.start()
    pre_polite_body = body_content[:earliest_pos]

    scan_area = head_content + "\n" + pre_polite_body

    # Find referenced files: <script src>, <link href>, <img src>
    refs = set()
    for m in re.finditer(r'<script[^>]+src\s*=\s*["\']([^"\']+)["\']', scan_area, re.I):
        refs.add(m.group(1))
    for m in re.finditer(r'<link[^>]+href\s*=\s*["\']([^"\']+)["\']', scan_area, re.I):
        refs.add(m.group(1))
    for m in re.finditer(r'<img[^>]+src\s*=\s*["\']([^"\']+)["\']', scan_area, re.I):
        refs.add(m.group(1))

    # CSS background-image and @import in inline <style> blocks
    style_blocks = re.findall(r'<style[^>]*>(.*?)</style>', scan_area, re.I | re.S)
    style_content = "\n".join(style_blocks)
    for m in re.finditer(r'url\s*\(\s*["\']?([^"\')\s]+)["\']?\s*\)', style_content, re.I):
        refs.add(m.group(1))
    for m in re.finditer(r'@import\s+(?:url\s*\(\s*)?["\']([^"\']+)["\']', style_content, re.I):
        refs.add(m.group(1))

    # Match references to ZIP entries and sum sizes
    total_bytes = 0
    matched_files = []
    for ref in refs:
        if ref.startswith(("http://", "https://", "//")):
            continue
        ref_lower = ref.lower().lstrip("./")
        basename = os.path.basename(ref_lower)
        size = size_lookup.get(ref_lower) or size_lookup.get(basename)
        if size is not None:
            total_bytes += size
            matched_files.append(ref)

    return total_bytes, matched_files


# ── Shared check helpers ────────────────────────────────────────────────────

def _check_animation_duration(check_id, css_text, primary_html, js_text, threshold_s):
    """Check CSS animation duration and JS timers against a threshold."""
    combined = css_text + " " + primary_html
    durs = re.findall(r"animation-duration\s*:\s*([\d.]+)s", combined)
    max_dur = max((float(d) for d in durs), default=0)
    long_timers = [int(t) for t in
                   re.findall(r"setTimeout\s*\([^,]+,\s*(\d+)", js_text) +
                   re.findall(r"setInterval\s*\([^,]+,\s*(\d+)", js_text)
                   if int(t) > threshold_s * 1000]

    if max_dur > threshold_s or long_timers:
        parts = []
        if max_dur > threshold_s:
            parts.append(f"CSS animation-duration: {max_dur}s exceeds {threshold_s}s limit (advisory — check if this applies to the main animation flow)")
        if long_timers:
            parts.append(f"JS timer > {threshold_s}s: {long_timers[0]}ms")
        suggestion = f"Limit animation to {threshold_s}s, then freeze to static." if threshold_s <= 15 else f"Limit animation to {threshold_s}s."
        return CheckResult(id=check_id, status="WARNING", message="; ".join(parts), suggestion=suggestion)
    return CheckResult(id=check_id, status="PASS", message="No animation duration issues")


def _check_infinite_loop(check_id, css_text, primary_html, max_iterations=None):
    """Check for infinite CSS animation loops, optionally with iteration count limit."""
    combined = css_text + " " + primary_html
    inf_loop = (bool(re.search(r"animation-iteration-count\s*:\s*infinite", combined, re.I)) or
                bool(re.search(r"animation\s*:[^;]*\binfinite\b", combined, re.I)))

    if max_iterations is not None:
        high_iter = re.findall(r"animation-iteration-count\s*:\s*(\d+)", combined, re.I)
        over_max = any(int(x) > max_iterations for x in high_iter) if high_iter else False
        loop_issue = inf_loop or over_max
        if loop_issue:
            msg = "Infinite animation loop in CSS" if inf_loop else f"Animation iteration count > {max_iterations}"
            return CheckResult(id=check_id, status="WARNING", message=msg,
                               suggestion=f"Limit to max {max_iterations} loops, no infinite.")
        return CheckResult(id=check_id, status="PASS",
                           message=f"Animation loops within limit (max {max_iterations})")

    return CheckResult(id=check_id, status="WARNING" if inf_loop else "PASS",
                       message="CSS animation-iteration-count: infinite (advisory — check if intentional or in a conditional class)" if inf_loop else "No infinite loops",
                       suggestion="Remove or limit infinite animation loops." if inf_loop else None)


def _check_audio_autoplay(check_id, all_text):
    """Check for audio autoplay."""
    audio_auto = (bool(re.search(r"<audio[^>]*\bautoplay\b", all_text, re.I)) or
                  bool(re.search(r"new\s+Audio\s*\([^)]*\)\s*\.play\s*\(", all_text)))
    return CheckResult(id=check_id, status="FAIL" if audio_auto else "PASS",
                       message="Audio autoplay detected" if audio_auto else "No audio autoplay",
                       suggestion="Remove autoplay." if audio_auto else None)


def _check_video_muted(check_id, all_text):
    """Check that video tags have muted attribute."""
    video_tags = re.findall(r"<video[^>]*>", all_text, re.I)
    unmuted = [v for v in video_tags if "muted" not in v.lower()]
    return CheckResult(id=check_id, status="FAIL" if video_tags and unmuted else "PASS",
                       message=f"Video without muted ({len(unmuted)})" if video_tags and unmuted else "No unmuted video",
                       suggestion="Add muted to <video>." if video_tags and unmuted else None)


def scan_zip(zip_path, platforms, allowed_domains=None):
    """Scan a single ZIP file against specified platforms. Returns list of banner results."""
    zip_name = os.path.basename(zip_path)
    ext = os.path.splitext(zip_name)[1].lower()
    file_size = os.path.getsize(zip_path)
    banner_results = []

    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile:
        for p in platforms:
            banner_results.append(BannerResult(
                filename=zip_name, platform=p,
                metadata={"declared_size": None, "file_count": 0, "total_size_kb": 0, "is_rich_media": False},
                checks=[CheckResult(id=f"{p}-PKG-01", status="FAIL", message="Not a valid ZIP archive", suggestion="Re-package as a valid ZIP.")],
            ))
        return banner_results

    raw_infolist = zf.infolist()
    infos = [i for i in raw_infolist if not i.is_dir() and not i.filename.startswith("__MACOSX")]
    filenames = [i.filename for i in infos]
    total_uncomp = sum(i.file_size for i in infos)

    # Read text files
    text_contents = {}
    for info in infos:
        fext = os.path.splitext(info.filename)[1].lower()
        if fext in TEXT_EXTS:
            try:
                text_contents[info.filename] = zf.read(info.filename).decode("utf-8", errors="replace")
            except Exception:
                text_contents[info.filename] = ""

    all_text = "\n".join(text_contents.values())

    # Aggregated JS and CSS content (replaces inline computation in DV360 block)
    js_text = "\n".join(v for k, v in text_contents.items() if k.endswith(".js"))
    css_text = "\n".join(v for k, v in text_contents.items() if k.endswith(".css"))

    # Junk file detection (scan raw infolist including __MACOSX)
    junk_files = []
    junk_bytes = 0
    for info in raw_infolist:
        if info.is_dir():
            continue
        basename = os.path.basename(info.filename).lower()
        is_macosx = info.filename.startswith("__MACOSX")
        is_git = "/.git/" in info.filename or info.filename.startswith(".git/")
        is_junk_name = basename in JUNK_NAMES
        if is_macosx or is_git or is_junk_name:
            junk_files.append(info.filename)
            junk_bytes += info.file_size

    # Find primary HTML
    root_htmls = [f for f in filenames if "/" not in f and os.path.splitext(f)[1].lower() in (".html", ".htm")]
    primary_html_name = None
    if root_htmls:
        primary_html_name = next((c for c in root_htmls if c.lower() == "index.html"), root_htmls[0])
    else:
        all_htmls = [f for f in filenames if os.path.splitext(f)[1].lower() in (".html", ".htm")]
        if all_htmls:
            primary_html_name = all_htmls[0]
    primary_html = text_contents.get(primary_html_name, "") if primary_html_name else ""

    # Detect single-folder wrapper (common macOS Archive Utility pattern)
    non_junk_filenames = [f for f in filenames if not f.startswith("__MACOSX")]
    _root_prefixes = set(f.split("/")[0] for f in non_junk_filenames if "/" in f)
    _all_in_subfolder = bool(_root_prefixes) and all("/" in f for f in non_junk_filenames)
    _single_wrapper_folder = _root_prefixes.pop() if _all_in_subfolder and len(_root_prefixes) == 1 else None

    # Initial load estimate
    initial_bytes, initial_files = estimate_initial_load(primary_html, infos)

    # Read manifest.json if present (Adform)
    manifest_data = None
    if "manifest.json" in filenames:
        try:
            manifest_data = json.loads(zf.read("manifest.json").decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, Exception):
            manifest_data = "INVALID"

    # Detect rich media
    is_rich = "Enabler.js" in all_text

    # Ad size — check meta tag first, then GWD CSS fallback (.gwd-page-size)
    ad_m = re.search(r'<meta\s+name=["\']ad\.size["\']\s+content=["\']width=(\d+),\s*height=(\d+)["\']', primary_html, re.I)
    gwd_size_m = re.search(r'\.gwd-page-size\s*\{[^}]*width\s*:\s*(\d+)px\s*;\s*height\s*:\s*(\d+)px', primary_html, re.I) if not ad_m else None
    declared_size = f"{ad_m.group(1)}x{ad_m.group(2)}" if ad_m else (f"{gwd_size_m.group(1)}x{gwd_size_m.group(2)}" if gwd_size_m else None)
    ad_width = int(ad_m.group(1)) if ad_m else (int(gwd_size_m.group(1)) if gwd_size_m else None)

    for platform in platforms:
        checks = []
        meta = {
            "declared_size": declared_size,
            "file_count": len(infos),
            "total_size_kb": round(total_uncomp / 1024, 1),
            "is_rich_media": is_rich,
            "initial_load_kb": round(initial_bytes / 1024, 1),
            "clicktag_vars": [],
        }
        if platform == "CM360":
            ALLOWED = CM360_ALLOWED
        elif platform == "DV360":
            ALLOWED = DV360_ALLOWED
        elif platform == "ADFORM":
            ALLOWED = ADFORM_ALLOWED
        elif platform == "AMAZONDSP":
            ALLOWED = AMAZONDSP_ALLOWED
        else:
            ALLOWED = TTD_ALLOWED

        # ── PKG-01: Archive Format ──
        if platform == "CM360":
            ok = ext in (".zip", ".adz")
            checks.append(CheckResult(id= "CM360-PKG-01", status= "PASS" if ok else "FAIL",
                           message= f"Archive format is {ext}" if ok else f"Format {ext} not allowed",
                           suggestion= None if ok else "Re-package as .zip or .adz"))
        else:
            ok = ext == ".zip"
            checks.append(CheckResult(id= f"{platform}-PKG-01", status= "PASS" if ok else "FAIL",
                           message= "Archive format is .zip" if ok else f"Format {ext} not allowed",
                           suggestion= None if ok else "Re-package as .zip"))

        # ── ADFORM-PKG-02 to PKG-04: manifest.json checks ──
        if platform == "ADFORM":
            has_manifest = "manifest.json" in filenames
            checks.append(CheckResult(id= "ADFORM-PKG-02", status= "PASS" if has_manifest else "FAIL",
                           message= "manifest.json present" if has_manifest else "manifest.json not found",
                           suggestion= None if has_manifest else "Add manifest.json to ZIP root."))

            if has_manifest and isinstance(manifest_data, dict):
                required_keys = {"version", "title", "width", "height", "source"}
                missing_keys = required_keys - set(manifest_data.keys())
                ok = not missing_keys
                checks.append(CheckResult(id= "ADFORM-PKG-03", status= "PASS" if ok else "FAIL",
                               message= "manifest.json valid" if ok else f"manifest.json missing keys: {', '.join(sorted(missing_keys))}",
                               suggestion= None if ok else f"Add required fields: {', '.join(sorted(required_keys))}"))

                source_file = manifest_data.get("source", "")
                source_exists = source_file in filenames
                checks.append(CheckResult(id= "ADFORM-PKG-04", status= "PASS" if source_exists else "FAIL",
                               message= f"Source file present: {source_file}" if source_exists else f"Source file missing: {source_file}",
                               suggestion= None if source_exists else f"Add {source_file} to ZIP root or fix manifest.json source field."))
            elif has_manifest:
                checks.append(CheckResult(id= "ADFORM-PKG-03", status= "FAIL",
                               message= "manifest.json is not valid JSON",
                               suggestion= "Fix JSON syntax in manifest.json."))
                checks.append(CheckResult(id= "ADFORM-PKG-04", status= "FAIL",
                               message= "Cannot verify source file (invalid manifest)",
                               suggestion= "Fix manifest.json first."))

        # ── PKG-02: File Count (non-Adform, non-AmazonDSP) ──
        if platform not in ("ADFORM", "AMAZONDSP"):
            ok = len(infos) <= 100
            checks.append(CheckResult(id= f"{platform}-PKG-02", status= "PASS" if ok else "FAIL",
                           message= f"File count: {len(infos)} (limit: 100)",
                           suggestion= None if ok else "Reduce to 100 or fewer."))

        # ── PKG-03/PKG-05: Package Size ──
        if platform == "AMAZONDSP":
            lim, ll = 204_800, "200 KB"
        elif platform == "ADFORM":
            lim, ll = 307_200, "300 KB"
        elif platform == "DV360":
            lim, ll = 5_242_880, "5 MB"
        else:  # CM360, TTD
            lim, ll = 10_485_760, "10 MB"
        ok = file_size <= lim
        if platform == "ADFORM":
            size_check_id = "ADFORM-PKG-05"
        elif platform == "AMAZONDSP":
            size_check_id = "AMAZONDSP-PKG-02"
        else:
            size_check_id = f"{platform}-PKG-03"
        checks.append(CheckResult(id= size_check_id, status= "PASS" if ok else "FAIL",
                       message= f"Package size: {round(file_size / 1024, 1)} KB (limit: {ll})",
                       suggestion= None if ok else f"Reduce to under {ll}."))

        # ── GEN-PERF-01: Chrome Heavy Ad Threshold ──
        ok = total_uncomp <= HEAVY_AD_THRESHOLD
        checks.append(CheckResult(id= "GEN-PERF-01", status= "PASS" if ok else "WARNING",
                       message= f"Total uncompressed: {round(total_uncomp / 1024, 1)} KB (Heavy Ad limit: 4 MB)" if ok
                       else f"Total uncompressed: {round(total_uncomp / 1024, 1)} KB exceeds 4 MB Heavy Ad threshold",
                       suggestion= None if ok else "Reduce total uncompressed size below 4 MB to avoid Chrome Heavy Ad intervention."))

        # ── DV360-PKG-04: Filename Length ──
        if platform == "DV360":
            _av_exts = {".mp3", ".mp4", ".ogg", ".wav", ".webm", ".avi", ".mov", ".flv"}
            long_n = []
            for f in filenames:
                ext = os.path.splitext(f)[1].lower()
                limit = 50 if ext in _av_exts else 200
                if len(f) > limit:
                    long_n.append(f)
            checks.append(CheckResult(id= "DV360-PKG-04", status= "PASS" if not long_n else "FAIL",
                           message= "All filenames within length limits" if not long_n
                           else f"{len(long_n)} filename(s) exceed limit: {long_n[0]}",
                           suggestion= None if not long_n else "Shorten filenames (200 chars max, 50 for audio/video)."))

        # ── TTD-PKG-04: Uncompressed Size Limit ──
        if platform == "TTD":
            ttd_uncomp_lim = 12_582_912  # 12 MB
            ok = total_uncomp <= ttd_uncomp_lim
            checks.append(CheckResult(id= "TTD-PKG-04", status= "PASS" if ok else "FAIL",
                           message= f"Uncompressed size: {round(total_uncomp / 1024, 1)} KB (limit: 12 MB)",
                           suggestion= None if ok else "Reduce total uncompressed size below 12 MB."))

        # ── PKG Primary HTML (Adform uses ADFORM-PKG-04 from manifest check above) ──
        if platform == "AMAZONDSP":
            has_index = "index.html" in filenames
            checks.append(CheckResult(id= "AMAZONDSP-PKG-03", status= "PASS" if has_index else "FAIL",
                           message= "index.html found at ZIP root" if has_index else "index.html not found at ZIP root",
                           suggestion= None if has_index else "Add index.html to the ZIP root."))
        elif platform != "ADFORM":
            hid = {"CM360": "CM360-PKG-04", "DV360": "DV360-PKG-05", "TTD": "TTD-PKG-05"}[platform]
            if root_htmls:
                _pkg_status = "PASS"
                _pkg_msg = f"Primary HTML: {primary_html_name}"
                _pkg_sug = None
            elif _single_wrapper_folder and primary_html_name:
                _pkg_status = "WARNING"
                _pkg_msg = (f"HTML inside wrapper folder '{_single_wrapper_folder}/' "
                            f"(macOS Archive Utility pattern) — spec requires HTML at ZIP root")
                _pkg_sug = f"Re-zip from inside the folder: cd '{_single_wrapper_folder}' && zip -r ../banner.zip *"
            elif primary_html_name:
                _pkg_status = "FAIL"
                _pkg_msg = f"HTML not at ZIP root (found: {primary_html_name})"
                _pkg_sug = "Place the HTML file directly at the archive root."
            else:
                _pkg_status = "FAIL"
                _pkg_msg = "No .html/.htm found in archive"
                _pkg_sug = "Place HTML file at archive root."
            checks.append(CheckResult(id=hid, status=_pkg_status, message=_pkg_msg, suggestion=_pkg_sug))

        # ── FILE-01: Allowed File Types ──
        dis = [f"{os.path.splitext(f)[1].lower()} ({f})" for f in filenames
               if os.path.splitext(f)[1].lower() and os.path.splitext(f)[1].lower() not in ALLOWED]
        checks.append(CheckResult(id= f"{platform}-FILE-01", status= "PASS" if not dis else "FAIL",
                       message= "All file types allowed" if not dis else f"Disallowed: {'; '.join(dis[:3])}",
                       suggestion= None if not dis else f"Remove disallowed files. Allowed: {', '.join(sorted(ALLOWED))}"))

        # ── FILE-02: No Nested ZIPs ──
        nested = [f for f in filenames if os.path.splitext(f)[1].lower() in (".zip", ".adz")]
        checks.append(CheckResult(id= f"{platform}-FILE-02", status= "PASS" if not nested else "FAIL",
                       message= "No nested ZIPs" if not nested else f"Nested: {', '.join(nested)}",
                       suggestion= None if not nested else "Remove nested archives."))

        # ── TTD-FILE-03: Primary HTML File Size ──
        if platform == "TTD" and primary_html_name:
            primary_info = next((i for i in infos if i.filename == primary_html_name), None)
            if primary_info:
                primary_size = primary_info.file_size
                ok = primary_size <= 102_400  # 100 KB
                checks.append(CheckResult(id= "TTD-FILE-03", status= "PASS" if ok else "FAIL",
                               message= f"Primary HTML size: {round(primary_size / 1024, 1)} KB (limit: 100 KB)",
                               suggestion= None if ok else "Reduce primary HTML file to under 100 KB."))

        # ── TTD-FILE-04: Individual File Size ──
        if platform == "TTD":
            ttd_file_lim = 2_306_867  # 2.2 MB
            large_files = [(i.filename, i.file_size) for i in infos if i.file_size > ttd_file_lim]
            if large_files:
                f_name, f_size = large_files[0]
                checks.append(CheckResult(id= "TTD-FILE-04", status= "FAIL",
                               message= f"File exceeds 2.2 MB: {f_name} ({round(f_size / 1024, 1)} KB)",
                               suggestion= "Reduce individual file sizes to under 2.2 MB."))
            else:
                checks.append(CheckResult(id= "TTD-FILE-04", status= "PASS",
                               message= "All individual files within 2.2 MB limit",
                               suggestion= None))

        # ── GEN-PKG-06: Zero-Byte Files ──
        zero_files = [i.filename for i in infos if i.file_size == 0]
        checks.append(CheckResult(id= "GEN-PKG-06", status= "PASS" if not zero_files else "WARNING",
                       message= "No zero-byte files" if not zero_files
                       else f"Zero-byte file(s): {', '.join(zero_files[:3])}",
                       suggestion= None if not zero_files else "Remove empty files from the archive."))

        # ── GEN-PKG-07: Junk Files ──
        junk_msg = "No junk files"
        if junk_files:
            mac_junk = [f for f in junk_files if f.startswith("__MACOSX") or os.path.basename(f).startswith("._") or os.path.basename(f).lower() == ".ds_store"]
            other_junk = [f for f in junk_files if f not in mac_junk]
            parts = []
            if mac_junk:
                parts.append(f"macOS metadata ({len(mac_junk)} file(s): __MACOSX/, ._*, .DS_Store)")
            if other_junk:
                parts.append(f"other junk ({len(other_junk)}): {', '.join(other_junk[:2])}")
            junk_msg = "; ".join(parts)
            junk_sug = ("macOS Archive Utility adds these automatically. Re-zip from inside the banner folder: "
                        "cd 'banner-folder' && zip -r ../banner.zip *")
        else:
            junk_sug = None
        checks.append(CheckResult(id= "GEN-PKG-07", status= "PASS" if not junk_files else "WARNING",
                       message= junk_msg,
                       suggestion= junk_sug))

        # ── HTML-01: Ad Size ──
        if platform == "ADFORM" and isinstance(manifest_data, dict):
            mw = manifest_data.get("width")
            mh = manifest_data.get("height")
            manifest_size_ok = (isinstance(mw, int) and isinstance(mh, int) and mw > 0 and mh > 0)
            if manifest_size_ok:
                checks.append(CheckResult(id= "ADFORM-HTML-01", status= "PASS",
                               message= f"Ad size from manifest.json: width={mw},height={mh}",
                               suggestion= None))
            elif ad_m:
                checks.append(CheckResult(id= "ADFORM-HTML-01", status= "PASS",
                               message= f"Ad size from meta tag (manifest fallback): width={ad_m.group(1)},height={ad_m.group(2)}",
                               suggestion= None))
            else:
                checks.append(CheckResult(id= "ADFORM-HTML-01", status= "FAIL",
                               message= "Ad size not found in manifest.json or meta tag",
                               suggestion= 'Set width/height in manifest.json or add <meta name="ad.size" content="width=X,height=Y">.'))
        else:
            ad_size_ok = ad_m or gwd_size_m
            if ad_m:
                ad_size_msg = f"Ad size meta tag: width={ad_m.group(1)},height={ad_m.group(2)}"
            elif gwd_size_m:
                ad_size_msg = f"Ad size from GWD CSS: width={gwd_size_m.group(1)},height={gwd_size_m.group(2)}"
            else:
                ad_size_msg = "Ad size meta tag not found"
            checks.append(CheckResult(id= f"{platform}-HTML-01", status= "PASS" if ad_size_ok else "FAIL",
                           message= ad_size_msg,
                           suggestion= None if ad_size_ok else 'Add <meta name="ad.size" content="width=X,height=Y"> to <head>.'))

        # ── HTML-02: Valid Structure ──
        hl = primary_html.lower()
        miss = [t.replace("<", "").replace("!", "") for t in ["<!doctype html", "<html", "<head", "<body"] if t not in hl]
        checks.append(CheckResult(id= f"{platform}-HTML-02", status= "PASS" if not miss else "WARNING",
                       message= "Valid HTML structure" if not miss else f"Missing: {', '.join(miss)}",
                       suggestion= None if not miss else "Include <!DOCTYPE html>, <html>, <head>, <body>."))

        # ── GEN-HTML-03: Viewport Meta (Mobile) ──
        if ad_width is not None and ad_width <= 320:
            has_viewport = bool(re.search(r'<meta[^>]+name=["\']viewport["\']', primary_html, re.I))
            checks.append(CheckResult(id= "GEN-HTML-03", status= "PASS" if has_viewport else "WARNING",
                           message= f"Viewport meta tag found (mobile ad {declared_size})" if has_viewport
                           else f"No viewport meta tag for mobile ad ({declared_size})",
                           suggestion= None if has_viewport else 'Add <meta name="viewport" content="width=device-width, initial-scale=1"> for mobile ads.'))

        # ── ADFORM-DHTML-01: DHTML Library Reference ──
        if platform == "ADFORM":
            has_dhtml = bool(re.search(r"Adform\.DHTML\.js", all_text, re.I))
            checks.append(CheckResult(id= "ADFORM-DHTML-01", status= "PASS" if has_dhtml else "FAIL",
                           message= "Adform.DHTML.js reference found" if has_dhtml else "Adform.DHTML.js not found",
                           suggestion= None if has_dhtml else 'Add <script src="https://s1.adform.net/banners/scripts/rmb/Adform.DHTML.js"></script>.'))

        # ── Click Tracking ──
        if platform == "AMAZONDSP":
            sdk_click = bool(re.search(r"SDK\.clickThrough\s*\(", all_text))
            checks.append(CheckResult(id= "AMAZONDSP-CLICK-01", status= "PASS" if sdk_click else "FAIL",
                           message= "SDK.clickThrough() found" if sdk_click else "SDK.clickThrough() not found",
                           suggestion= None if sdk_click else "Add SDK.clickThrough() for click tracking."))

            # ── AMAZONDSP-JS-01: Restricted External Scripts ──
            ext_scripts = re.findall(r'<script[^>]+src\s*=\s*["\']https?://([^"\'/:]+)', all_text, re.I)
            bad_scripts = [d for d in ext_scripts if not d.endswith("adkit-advertising.amazon") and "adkit-advertising.amazon" not in d]
            checks.append(CheckResult(id= "AMAZONDSP-JS-01", status= "PASS" if not bad_scripts else "FAIL",
                           message= "No restricted external scripts" if not bad_scripts
                           else f"External script domain(s) not allowed: {', '.join(set(bad_scripts))}",
                           suggestion= None if not bad_scripts else "Only inline scripts or adkit-advertising.amazon domains are allowed."))
            meta["clicktag_vars"] = ["SDK.clickThrough()"] if sdk_click else []

        elif platform == "ADFORM":
            ct_found = bool(re.search(r'''dhtml\.getVar\s*\(\s*['"]clickTAG''', all_text))
            checks.append(CheckResult(id= "ADFORM-CLICK-01", status= "PASS" if ct_found else "FAIL",
                           message= "clickTAG via dhtml.getVar() found" if ct_found else "dhtml.getVar('clickTAG') not found",
                           suggestion= None if ct_found else "Use var clickTAGvalue = dhtml.getVar('clickTAG');"))

            if isinstance(manifest_data, dict):
                clicktags = manifest_data.get("clicktags", manifest_data.get("clickTags", {}))
                has_ct_in_manifest = isinstance(clicktags, dict) and "clickTAG" in clicktags
                checks.append(CheckResult(id= "ADFORM-CLICK-02", status= "PASS" if has_ct_in_manifest else "WARNING",
                               message= "clickTAG declared in manifest.json clicktags" if has_ct_in_manifest
                               else "clickTAG not found in manifest.json clicktags section",
                               suggestion= None if has_ct_in_manifest else 'Add "clicktags": {"clickTAG": ""} to manifest.json.'))
            else:
                checks.append(CheckResult(id= "ADFORM-CLICK-02", status= "WARNING",
                               message= "Cannot check clicktags (manifest.json missing or invalid)",
                               suggestion= "Add valid manifest.json with clicktags section."))
            meta["clicktag_vars"] = ["clickTAG (dhtml.getVar)"] if ct_found else []

        elif platform == "TTD":
            # TTD uses clickTAG (uppercase TAG)
            ct_pattern = r"\b(?:var|let|const)\s+(clickTAG\d*)\b|\b(window\.clickTAG\d*)\b"
            ct_matches = re.findall(ct_pattern, all_text)
            ct_vars = sorted(set((m[0] or m[1]).removeprefix("window.") for m in ct_matches))
            # Also check for getParameterByName("clickTAG") pattern
            gpbn = bool(re.search(r'getParameterByName\s*\(\s*["\']clickTAG["\']', all_text))
            ct_found = len(ct_vars) > 0 or gpbn

            if ct_found and len(ct_vars) > 1:
                msg = f"clickTAG variables: {', '.join(ct_vars)}"
            elif ct_found:
                msg = f"clickTAG variable: {ct_vars[0]}" if ct_vars else "clickTAG found (via getParameterByName)"
            else:
                msg = "clickTAG not found"

            checks.append(CheckResult(id= "TTD-CLICK-01", status= "PASS" if ct_found else "FAIL",
                           message= msg,
                           suggestion= None if ct_found else 'Define var clickTAG = getParameterByName("clickTAG");'))

            hc = re.search(r'''clickTAG\s*=\s*["']https?://''', all_text)
            if ct_found and not hc:
                checks.append(CheckResult(id= "TTD-CLICK-02", status= "PASS", message= "clickTAG not hardcoded", suggestion= None))
            elif hc:
                checks.append(CheckResult(id= "TTD-CLICK-02", status= "FAIL", message= "clickTAG hardcoded to a URL",
                               suggestion= "Use getParameterByName or empty string."))
            else:
                checks.append(CheckResult(id= "TTD-CLICK-02", status= "INFO", message= "clickTAG N/A", suggestion= None))
            meta["clicktag_vars"] = ct_vars if ct_vars else (["clickTAG (getParameterByName)"] if gpbn else [])

        elif platform == "CM360" or (platform == "DV360" and not is_rich):
            cp = f"{platform}-CLICK"

            # Find all clickTag variants (clickTag, clickTag1, clickTag2, etc.)
            ct_pattern = r"\b(?:var|let|const)\s+(clickTag\d*)\b|\b(window\.clickTag\d*)\b"
            ct_matches = re.findall(ct_pattern, all_text)
            ct_vars = sorted(set((m[0] or m[1]).removeprefix("window.") for m in ct_matches))

            # Also accept Enabler.exit("clickTag",...) and <gwd-exit metric="clickTag"> as valid click tracking
            enabler_exit_ct = re.findall(r'Enabler\.exit\s*\(\s*["\']clickTag\d*["\']', all_text)
            gwd_exit_ct = re.findall(r'<gwd-exit\s+[^>]*metric\s*=\s*["\']clickTag\d*["\']', all_text, re.I)
            ct_found = len(ct_vars) > 0 or bool(enabler_exit_ct) or bool(gwd_exit_ct)

            if ct_vars and len(ct_vars) > 1:
                msg = f"clickTag variables: {', '.join(ct_vars)}"
            elif ct_vars:
                msg = f"clickTag variable: {ct_vars[0]}"
            elif enabler_exit_ct or gwd_exit_ct:
                msg = "clickTag via Enabler.exit()/GWD exit event"
            else:
                msg = "clickTag not found"

            checks.append(CheckResult(id= f"{cp}-01", status= "PASS" if ct_found else "FAIL",
                           message= msg,
                           suggestion= None if ct_found else 'Define var clickTag = "";'))

            hc = re.search(r'''clickTag\s*=\s*["']https?://''', all_text)
            if ct_found and not hc:
                checks.append(CheckResult(id= f"{cp}-02", status= "PASS", message= "clickTag not hardcoded", suggestion= None))
            elif hc:
                checks.append(CheckResult(id= f"{cp}-02", status= "WARNING", message= "clickTag hardcoded to a URL",
                               suggestion= "Use an empty string or URL parameter — the ad server will inject the click URL at serve time."))
            else:
                checks.append(CheckResult(id= f"{cp}-02", status= "INFO", message= "clickTag N/A", suggestion= None))
            meta["clicktag_vars"] = ct_vars

            if platform == "CM360":
                js_ct = {k: v for k, v in text_contents.items() if k.endswith(".js") and "clickTag" in v}
                minf = any(
                    sum(len(l) for l in v.split("\n")) / max(len(v.split("\n")), 1) > 500
                    for v in js_ct.values()
                )
                checks.append(CheckResult(id= "CM360-CLICK-03", status= "WARNING" if minf else "PASS",
                               message= "clickTag code appears minified" if minf else "clickTag code is readable",
                               suggestion= "Provide unminified clickTag." if minf else None))

        # ── DV360 Rich Media ──
        if platform == "DV360" and is_rich:
            checks.append(CheckResult(id= "DV360-RICH-01", status= "INFO", message= "Enabler.js found - rich media", suggestion= None))

            # Extract exit names from Enabler.exit() calls
            exit_matches = re.findall(r'Enabler\.exit\s*\(\s*["\']([^"\']+)["\']', all_text)
            has_exit = bool(exit_matches) or bool(re.search(r"Enabler\.exit\s*\(", all_text))

            if exit_matches:
                exit_names = sorted(set(exit_matches))
                exit_msg = f"Enabler.exit() found — exits: {', '.join(exit_names)}"
            elif has_exit:
                exit_msg = "Enabler.exit() found"
            else:
                exit_msg = "No Enabler.exit()"

            checks.append(CheckResult(id= "DV360-RICH-02", status= "PASS" if has_exit else "FAIL",
                           message= exit_msg,
                           suggestion= None if has_exit else "Add Enabler.exit() for clicks."))
            ei = bool(re.search(r"Enabler\.isInitialized\s*\(", all_text)) or "StudioEvent.INIT" in all_text
            checks.append(CheckResult(id= "DV360-RICH-03", status= "PASS" if ei else "WARNING",
                           message= "Enabler init check found" if ei else "No Enabler init check",
                           suggestion= None if ei else "Add Enabler.isInitialized() check."))
            exit_names = sorted(set(exit_matches)) if exit_matches else []
            meta["clicktag_vars"] = [f"exit: {n}" for n in exit_names] if exit_names else (["Enabler.exit()"] if has_exit else [])

        # ── Security ──
        # Exclude HTTP URLs that appear only in comment/license blocks (not actual resource loads)
        _comment_url_domains = {"polymer.github.io", "creativecommons.org", "opensource.org", "www.apache.org", "www.mozilla.org"}
        http_urls_raw = re.findall(r"http://(?!www\.w3\.org)[^\s\"'<>(),;\\]+", all_text)
        http_urls_untrusted = []
        http_urls_trusted = []
        for url in http_urls_raw:
            domain_m = re.match(r"http://([^/:\s]+)", url)
            domain = domain_m.group(1).lower() if domain_m else ""
            if domain in _comment_url_domains:
                continue  # Skip known license/comment-only domains
            is_allowed = any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)
            if is_allowed:
                http_urls_trusted.append(url)
            else:
                http_urls_untrusted.append(url)
        if http_urls_untrusted:
            _sec01_status = "FAIL"
            _sec01_msg = f"HTTP URL(s) to untrusted domain ({len(http_urls_untrusted)}): {http_urls_untrusted[0][:60]}"
            _sec01_sug = "Change all http:// to https://."
        elif http_urls_trusted:
            _sec01_status = "WARNING"
            _sec01_msg = f"HTTP URL(s) to trusted domain ({len(http_urls_trusted)}): {http_urls_trusted[0][:60]} — upgrade to https://"
            _sec01_sug = "Change http:// to https:// even for known domains."
        else:
            _sec01_status, _sec01_msg, _sec01_sug = "PASS", "All URLs use HTTPS", None
        checks.append(CheckResult(id= f"{platform}-SEC-01", status= _sec01_status, message= _sec01_msg, suggestion= _sec01_sug))

        storage = [s for s in ["localStorage", "sessionStorage"] if s in all_text]
        checks.append(CheckResult(id= f"{platform}-SEC-02", status= "PASS" if not storage else "FAIL",
                       message= "No localStorage/sessionStorage" if not storage else f"Found: {', '.join(storage)}",
                       suggestion= None if not storage else "Remove storage API usage."))

        # ── GEN-JS-01: Debug Statements ──
        debug_patterns = [
            (r"\bconsole\.(log|debug)\s*\(", "console"),
            (r"\bdebugger\b", "debugger"),
        ]
        debug_found = []
        for pat, label in debug_patterns:
            if re.search(pat, js_text):
                debug_found.append(label)
        for pat, label in debug_patterns:
            if label not in debug_found and re.search(pat, primary_html):
                debug_found.append(label)
        checks.append(CheckResult(id= "GEN-JS-01", status= "PASS" if not debug_found else "WARNING",
                       message= "No debug statements" if not debug_found
                       else f"Debug statements found: {', '.join(debug_found)}",
                       suggestion= None if not debug_found else "Remove console.log/console.debug statements before publishing."))

        # ── GEN-JS-02: Bundled Libraries ──
        bundled_found = []
        for lib_name, lib_info in BUNDLED_LIBS.items():
            found_by_name = any(
                os.path.basename(f).lower() in lib_info["filenames"]
                for f in filenames
            )
            found_by_sig = any(re.search(sig, js_text) for sig in lib_info["signatures"])
            if found_by_name or found_by_sig:
                bundled_found.append(f"{lib_name} (CDN: {lib_info['cdn']})")
        checks.append(CheckResult(id= "GEN-JS-02", status= "PASS" if not bundled_found else "WARNING",
                       message= "No bundled libraries detected" if not bundled_found
                       else f"Bundled library: {'; '.join(bundled_found)}",
                       suggestion= None if not bundled_found else "Consider loading libraries from CDN to reduce package size."))

        # ── GEN-SEC-03: External Domains ──
        domain_pattern = r'https?://([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)'
        found_domains = set(re.findall(domain_pattern, all_text))

        # Collect click-through destination domains (not external resources)
        _clickthrough_domains = set()
        for m in re.findall(r'Enabler\.exit\s*\(\s*["\'][^"\']*["\']\s*,\s*["\']https?://([^/\s"\']+)', all_text):
            _clickthrough_domains.add(m.lower())
        for m in re.findall(r'<gwd-exit\s+[^>]*url\s*=\s*["\']https?://([^/\s"\']+)', all_text, re.I):
            _clickthrough_domains.add(m.lower())
        for m in re.findall(r'clickTag\s*=\s*["\']https?://([^/\s"\']+)', all_text):
            _clickthrough_domains.add(m.lower())
        for m in re.findall(r'window\.open\s*\(\s*["\']https?://([^/\s"\']+)', all_text):
            _clickthrough_domains.add(m.lower())

        # Domains to exclude: click destinations + license/comment domains
        _excluded_domains = _clickthrough_domains | _comment_url_domains

        unapproved = []
        for domain in found_domains:
            d = domain.lower()
            if d in _excluded_domains:
                continue
            if not any(d == allowed or d.endswith("." + allowed) for allowed in (allowed_domains if allowed_domains is not None else ALLOWED_DOMAINS)):
                unapproved.append(d)
        unapproved.sort()
        unapproved_msg = "All external domains approved"
        if unapproved:
            unapproved_msg = f"Unapproved domain(s): {', '.join(unapproved[:5])}"
            if len(unapproved) > 5:
                unapproved_msg += f" (+{len(unapproved) - 5} more)"
        checks.append(CheckResult(id= "GEN-SEC-03", status= "PASS" if not unapproved else "WARNING",
                       message= unapproved_msg,
                       suggestion= None if not unapproved else "Verify external domains are approved for ad serving."))

        # ── Animation duration (TTD/DV360/ADFORM/AMAZONDSP) ──
        ANIM_THRESHOLDS = {"TTD": 15, "DV360": 30, "ADFORM": 30, "AMAZONDSP": 15}
        if platform in ANIM_THRESHOLDS:
            checks.append(_check_animation_duration(
                f"{platform}-ANIM-01", css_text, primary_html, js_text, ANIM_THRESHOLDS[platform]))

        # ── Infinite loop (DV360/ADFORM/AMAZONDSP) ──
        LOOP_PLATFORMS = {"DV360": None, "ADFORM": None, "AMAZONDSP": 3}
        if platform in LOOP_PLATFORMS:
            checks.append(_check_infinite_loop(
                f"{platform}-ANIM-02", css_text, primary_html, max_iterations=LOOP_PLATFORMS[platform]))

        # ── Audio/Video (DV360/ADFORM/AMAZONDSP) ──
        if platform in ("DV360", "ADFORM", "AMAZONDSP"):
            checks.append(_check_audio_autoplay(f"{platform}-AV-01", all_text))
            checks.append(_check_video_muted(f"{platform}-AV-02", all_text))

        # ── DV360-AV-03: Video playsinline (DV360 only) ──
        if platform == "DV360":
            video_tags = re.findall(r"<video[^>]*>", all_text, re.I)
            no_playsinline = [v for v in video_tags if "playsinline" not in v.lower()]
            if video_tags and no_playsinline:
                checks.append(CheckResult(id= "DV360-AV-03", status= "WARNING",
                               message= f"<video> missing playsinline attribute ({len(no_playsinline)} tag(s))",
                               suggestion= "Add playsinline attribute to <video> for iOS compatibility."))
            else:
                checks.append(CheckResult(id= "DV360-AV-03", status= "PASS",
                               message= "All video tags have playsinline or no video present",
                               suggestion= None))

        # ── Polite Load ──
        polite_threshold = 307_200 if platform == "TTD" else 153_600  # 300 KB for TTD, 150 KB for CM360/DV360/Adform
        polite_threshold_label = "300 KB" if platform == "TTD" else "150 KB"
        if total_uncomp > polite_threshold:
            polite_pats = [
                r'''window\.addEventListener\s*\(\s*["']load["']''',
                r'''document\.addEventListener\s*\(\s*["']DOMContentLoaded["']''',
                r"Enabler\.isInitialized\s*\(",
                r"Enabler\.isPageLoaded\s*\(",
            ]
            polite = any(re.search(p, all_text) for p in polite_pats)
            sd = "detected" if polite else "not found"
            initial_kb = round(initial_bytes / 1024, 1)
            checks.append(CheckResult(id= f"{platform}-POLITE-01", status= "PASS" if polite else "WARNING",
                           message= f"Total: {meta['total_size_kb']} KB > {polite_threshold_label}; initial payload est: {initial_kb} KB; polite load {sd}",
                           suggestion= None if polite else "Implement polite loading."))

            if platform != "TTD":
                img_exts = {".jpg", ".jpeg", ".gif", ".png", ".svg"}
                large_imgs = [(i.filename, i.file_size) for i in infos
                              if os.path.splitext(i.filename)[1].lower() in img_exts and i.file_size > 40_960]
                if large_imgs:
                    checks.append(CheckResult(id= f"{platform}-POLITE-02", status= "WARNING",
                                   message= f"Image > 40 KB: {large_imgs[0][0]} ({round(large_imgs[0][1] / 1024, 1)} KB)",
                                   suggestion= "Keep initial image under 40 KB."))
                else:
                    checks.append(CheckResult(id= f"{platform}-POLITE-02", status= "PASS", message= "All images under 40 KB", suggestion= None))
        else:
            checks.append(CheckResult(id= f"{platform}-POLITE-01", status= "PASS",
                           message= f"Size {meta['total_size_kb']} KB <= {polite_threshold_label}; polite load not required",
                           suggestion= None))

        banner_results.append(BannerResult(filename=zip_name, platform=platform, metadata=meta, checks=checks))

    zf.close()
    return banner_results


def main():
    parser = argparse.ArgumentParser(description="HTML5 Spec Guard - Banner Scanner")
    parser.add_argument("--scan-dir", default="scan", help="Directory containing ZIP files")
    parser.add_argument("--platforms", default="cm360,dv360", help="Comma-separated: cm360, dv360, ttd, adform, both (cm360+dv360), or all")
    parser.add_argument("--pdf", help="If set, generate PDF report at this path")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--runtime", action="store_true",
                        help="Run CPU measurement via Playwright (~30s per banner)")
    parser.add_argument("--exit-code", action="store_true",
                        help="Exit with code 1 if any check FAILs (for CI/CD)")
    parser.add_argument("--allow-domain", action="append", default=[],
                        help="Additional trusted domain(s) for GEN-SEC-03 (repeatable)")
    args = parser.parse_args()

    platforms = []
    for p in args.platforms.upper().replace(" ", "").split(","):
        if p in ("CM360", "DV360", "TTD", "ADFORM", "AMAZONDSP"):
            platforms.append(p)
        elif p == "BOTH":
            platforms.extend(["CM360", "DV360"])
        elif p == "ALL":
            platforms.extend(["CM360", "DV360", "TTD", "ADFORM", "AMAZONDSP"])
    if not platforms:
        platforms = ["CM360", "DV360"]

    zips = sorted(
        os.path.join(args.scan_dir, f)
        for f in os.listdir(args.scan_dir)
        if f.lower().endswith((".zip", ".adz"))
    )

    if not zips:
        print("No ZIP/ADZ files found in scan directory.", file=sys.stderr)
        sys.exit(1)

    results = ScanResult(
        title="HTML5 Banner Compliance Report",
        scan_timestamp=datetime.now().isoformat(timespec="seconds"),
    )

    allowed_domains = ALLOWED_DOMAINS | set(args.allow_domain) if args.allow_domain else None

    for zip_path in zips:
        results.banners.extend(scan_zip(zip_path, platforms, allowed_domains=allowed_domains))

    # Runtime CPU measurement (GEN-PERF-02)
    if args.runtime:
        if RUNTIME_AVAILABLE:
            # Deduplicate: measure once per unique ZIP filename
            measured = {}
            for zip_path in zips:
                zip_name = os.path.basename(zip_path)
                if zip_name not in measured:
                    print(f"Measuring CPU: {zip_name} ...", file=sys.stderr)
                    measured[zip_name] = measure_banner_cpu(zip_path)

            # Insert GEN-PERF-02 right after GEN-PERF-01 in each banner result
            for banner in results.banners:
                result = measured.get(banner.filename)
                if not result:
                    continue

                # Find insertion point: right after GEN-PERF-01
                insert_idx = None
                for i, c in enumerate(banner.checks):
                    if c.id == "GEN-PERF-01":
                        insert_idx = i + 1
                        break
                if insert_idx is None:
                    insert_idx = len(banner.checks)

                if result["ok"]:
                    cpu = result["cpu_seconds"]
                    if result["exceeds"]:
                        check = CheckResult(
                            id="GEN-PERF-02",
                            status="WARNING",
                            message=f"CPU time: {cpu}s in 30s window exceeds 15s Heavy Ad threshold",
                            suggestion="Reduce CPU usage to avoid Chrome Heavy Ad intervention.",
                        )
                    else:
                        check = CheckResult(
                            id="GEN-PERF-02",
                            status="PASS",
                            message=f"CPU time: {cpu}s in 30s window (Heavy Ad limit: 15s)",
                        )
                else:
                    check = CheckResult(
                        id="GEN-PERF-02",
                        status="INFO",
                        message=f"Runtime CPU check skipped: {result['error']}",
                    )
                banner.checks.insert(insert_idx, check)

                if result["ok"] and "peak_heap_mb" in result:
                    heap_mb = result["peak_heap_mb"]
                    heap_exceeds = heap_mb > 50
                    heap_check = CheckResult(
                        id="GEN-PERF-03",
                        status="WARNING" if heap_exceeds else "PASS",
                        message=f"Peak JS heap: {heap_mb} MB in 30s window"
                            + (" — exceeds 50 MB threshold" if heap_exceeds else " (threshold: 50 MB)"),
                        suggestion="Reduce memory usage to avoid issues on low-end devices." if heap_exceeds else None,
                    )
                    banner.checks.insert(insert_idx + 1, heap_check)
        else:
            print("INFO: --runtime requires Playwright (pip install playwright). Skipping CPU measurement.", file=sys.stderr)

    # Summary to stderr
    for b in results.banners:
        counts = {"PASS": 0, "FAIL": 0, "WARNING": 0, "INFO": 0}
        for c in b.checks:
            counts[c.status] = counts.get(c.status, 0) + 1
        print(f"  {b.filename} ({b.platform}): {counts['PASS']} pass, {counts['FAIL']} fail, {counts['WARNING']} warn", file=sys.stderr)

    # Convert to dicts for JSON/PDF output
    results_dict = asdict(results)

    if args.json:
        json.dump(results_dict, sys.stdout, indent=2, ensure_ascii=False)

    if args.pdf:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, script_dir)
        from generate_report import generate_report
        generate_report(results_dict, args.pdf)
        print(f"Report: {args.pdf}", file=sys.stderr)

    if args.exit_code:
        has_fail = any(c.status == "FAIL" for b in results.banners for c in b.checks)
        sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
