#!/usr/bin/env python3
"""
HTML5 Spec Guard — PDF Report Generator

Generates a styled PDF compliance report from JSON scan results.

Usage:
    python generate_report.py --input results.json --output report.pdf
    cat results.json | python generate_report.py --output report.pdf
"""

import argparse
import json
import math
import sys
import os
from datetime import datetime

from fpdf import FPDF


# ── Text sanitisation ────────────────────────────────────────────────────────

_UNICODE_MAP = {
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u2026": "...", # ellipsis
    "\u00d7": "x",   # multiplication sign
    "\u2022": "*",   # bullet
    "\u2192": "->",  # right arrow
    "\u2190": "<-",  # left arrow
}


def _safe(text: str) -> str:
    """Replace Unicode chars that Helvetica/latin-1 cannot encode."""
    for char, repl in _UNICODE_MAP.items():
        text = text.replace(char, repl)
    # fallback: drop anything still outside latin-1
    return text.encode("latin-1", errors="replace").decode("latin-1")


# ── Colours ──────────────────────────────────────────────────────────────────

COLORS = {
    "PASS":    (39, 174, 96),    # green
    "FAIL":    (231, 76, 60),    # red
    "WARNING": (241, 196, 15),   # amber
    "INFO":    (52, 152, 219),   # blue
}

HEADER_BG   = (44, 62, 80)      # dark blue-grey
HEADER_FG   = (255, 255, 255)
ROW_ALT     = (245, 245, 245)   # light grey alternating rows
BORDER_CLR  = (189, 195, 199)


# ── PDF class ────────────────────────────────────────────────────────────────

class ReportPDF(FPDF):

    def __init__(self, title: str, **kwargs):
        super().__init__(**kwargs)
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=20)

    # ── header / footer ──────────────────────────────────────────────────

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*HEADER_BG)
        self.cell(0, 8, _safe(self.report_title), align="L")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, datetime.now().strftime("%Y-%m-%d %H:%M"), align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BORDER_CLR)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(160, 160, 160)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    # ── helper: section heading ──────────────────────────────────────────

    def section_heading(self, text: str, level: int = 1):
        sizes = {1: 16, 2: 13, 3: 11}
        self.ln(4)
        self.set_font("Helvetica", "B", sizes.get(level, 11))
        self.set_text_color(*HEADER_BG)
        self.cell(0, 8, _safe(text), new_x="LMARGIN", new_y="NEXT")
        if level == 1:
            self.set_draw_color(*HEADER_BG)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    # ── helper: status badge ─────────────────────────────────────────────

    def status_badge(self, status: str, x: float, y: float, w: float = 22, h: float = 6):
        colour = COLORS.get(status, (100, 100, 100))
        self.set_fill_color(*colour)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        self.set_xy(x, y)
        self.cell(w, h, status, align="C", fill=True)

    # ── summary table ────────────────────────────────────────────────────

    def summary_table(self, banners: list):
        self.section_heading("Summary", level=1)

        col_w = [70, 30, 25, 25, 25, 25]
        headers = ["Banner", "Platform", "Pass", "Fail", "Warn", "Info"]

        # header row
        self.set_fill_color(*HEADER_BG)
        self.set_text_color(*HEADER_FG)
        self.set_font("Helvetica", "B", 9)
        for i, h in enumerate(headers):
            self.cell(col_w[i], 8, h, border=1, align="C", fill=True)
        self.ln()

        # data rows
        self.set_font("Helvetica", "", 9)
        for idx, b in enumerate(banners):
            counts = _count_statuses(b.get("checks", []))
            if idx % 2 == 1:
                self.set_fill_color(*ROW_ALT)
                fill = True
            else:
                self.set_fill_color(255, 255, 255)
                fill = True

            self.set_text_color(0, 0, 0)

            name = b.get("filename", "unknown")
            if len(name) > 30:
                name = name[:27] + "..."
            self.cell(col_w[0], 7, _safe(name), border=1, fill=fill)
            self.cell(col_w[1], 7, _safe(b.get("platform", "-")), border=1, align="C", fill=fill)

            for key, colour in [("PASS", COLORS["PASS"]), ("FAIL", COLORS["FAIL"]),
                                ("WARNING", COLORS["WARNING"]), ("INFO", COLORS["INFO"])]:
                val = str(counts.get(key, 0))
                if counts.get(key, 0) > 0 and key == "FAIL":
                    self.set_text_color(*colour)
                    self.set_font("Helvetica", "B", 9)
                else:
                    self.set_text_color(0, 0, 0)
                    self.set_font("Helvetica", "", 9)
                self.cell(col_w[headers.index({"WARNING": "Warn", "INFO": "Info"}.get(key, key.title()))],
                          7, val, border=1, align="C", fill=fill)
            self.ln()

    # ── checks table header helper ────────────────────────────────────────

    def _draw_checks_header(self, col_w):
        self.set_fill_color(*HEADER_BG)
        self.set_text_color(*HEADER_FG)
        self.set_font("Helvetica", "B", 8)
        self.cell(col_w[0], 7, "Check ID", border=1, fill=True)
        self.cell(col_w[1], 7, "Status", border=1, align="C", fill=True)
        self.cell(col_w[2], 7, "Details", border=1, fill=True)
        self.ln()

    # ── detail section for one banner ────────────────────────────────────

    def banner_detail(self, banner: dict):
        filename = banner.get("filename", "unknown")
        platform = banner.get("platform", "-")
        self.section_heading(f"{filename}  ({platform})", level=2)

        # banner metadata
        meta = banner.get("metadata", {})
        if meta:
            self.set_font("Helvetica", "", 9)
            self.set_text_color(80, 80, 80)
            parts = []
            if meta.get("declared_size"):
                parts.append(f"Declared size: {meta['declared_size']}")
            if meta.get("file_count") is not None:
                parts.append(f"Files: {meta['file_count']}")
            if meta.get("total_size_kb") is not None:
                parts.append(f"Total: {meta['total_size_kb']:.1f} KB")
            if meta.get("is_rich_media"):
                parts.append("Rich media (Enabler)")
            if meta.get("clicktag_vars"):
                parts.append(f"Click vars: {', '.join(meta['clicktag_vars'])}")
            if parts:
                self.cell(0, 5, _safe("  |  ".join(parts)), new_x="LMARGIN", new_y="NEXT")
                self.ln(2)

        # checks table
        col_w = [28, 22, 140]
        self._draw_checks_header(col_w)

        line_h = 6
        row_h = line_h  # minimum row height
        for idx, check in enumerate(banner.get("checks", [])):
            status = check.get("status", "INFO")
            check_id = check.get("id", "-")
            message = check.get("message", "")
            msg_safe = _safe(message)

            # Page-break protection: if not enough room, break and redraw header
            if self.get_y() + row_h > self.h - self.b_margin:
                self.add_page()
                self._draw_checks_header(col_w)

            if idx % 2 == 1:
                self.set_fill_color(*ROW_ALT)
            else:
                self.set_fill_color(255, 255, 255)

            x_start = self.get_x()
            y_start = self.get_y()

            # 1. Render Details (multi_cell) first to measure actual height
            msg_x = x_start + col_w[0] + col_w[1]
            self.set_xy(msg_x, y_start)
            self.set_text_color(0, 0, 0)
            self.set_font("Helvetica", "", 8)
            page_before = self.page
            self.multi_cell(col_w[2], line_h, msg_safe, border=1, fill=True)
            actual_y_after = self.get_y()

            if self.page == page_before:
                actual_row_h = max(actual_y_after - y_start, row_h)
            else:
                actual_row_h = row_h

            # 2. Draw Check ID and Status with the true height
            self.set_xy(x_start, y_start)
            self.set_text_color(0, 0, 0)
            self.set_font("Helvetica", "", 8)
            self.cell(col_w[0], actual_row_h, _safe(check_id), border=1, fill=True)

            colour = COLORS.get(status, (100, 100, 100))
            self.set_text_color(*colour)
            self.set_font("Helvetica", "B", 8)
            self.cell(col_w[1], actual_row_h, status, border=1, align="C", fill=True)

            # 3. Move cursor to next row
            self.set_xy(x_start, y_start + actual_row_h)

    # ── fix suggestions ──────────────────────────────────────────────────

    def fix_suggestions(self, banners: list):
        PLATFORM_DISPLAY = {
            "CM360": "CM360",
            "DV360": "DV360",
            "TTD": "The Trade Desk",
            "ADFORM": "Adform",
            "AMAZONDSP": "Amazon DSP",
        }

        # Collect failed checks grouped by platform; deduplicate GEN-* by (filename, check_id)
        groups: dict[str, list[dict]] = {}
        seen_general: set[tuple[str, str]] = set()

        for b in banners:
            filename = b.get("filename", "unknown")
            platform = b.get("platform", "Unknown")
            for c in b.get("checks", []):
                if c.get("status") != "FAIL" or not c.get("suggestion"):
                    continue
                check_id = c.get("id", "-")
                item = {"filename": filename, "id": check_id, "suggestion": c["suggestion"]}

                if check_id.startswith("GEN-"):
                    key = (filename, check_id)
                    if key in seen_general:
                        continue
                    seen_general.add(key)
                    groups.setdefault("General", []).append(item)
                else:
                    groups.setdefault(platform, []).append(item)

        if not groups:
            return

        self.add_page()
        self.section_heading("Fix Suggestions", level=1)

        # Render platform groups first (in insertion order), then "General" last
        general = groups.pop("General", None)
        for platform, items in groups.items():
            label = PLATFORM_DISPLAY.get(platform, platform)
            self.section_heading(label, level=2)
            self._render_fix_items(items)
        if general:
            self.section_heading("General", level=2)
            self._render_fix_items(general)

    def _render_fix_items(self, items: list[dict]):
        for item in items:
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*COLORS["FAIL"])
            self.cell(0, 6, _safe(f"{item['filename']} - {item['id']}"), new_x="LMARGIN", new_y="NEXT")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(60, 60, 60)
            self.multi_cell(0, 5, _safe(item["suggestion"]))
            self.ln(2)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _count_statuses(checks: list) -> dict:
    counts = {"PASS": 0, "FAIL": 0, "WARNING": 0, "INFO": 0}
    for c in checks:
        s = c.get("status", "INFO")
        counts[s] = counts.get(s, 0) + 1
    return counts


# ── Main ─────────────────────────────────────────────────────────────────────

def generate_report(data: dict, output_path: str):
    """Generate PDF report from scan results dict."""

    title = data.get("title", "HTML5 Banner Compliance Report")
    banners = data.get("banners", [])
    scan_ts = data.get("scan_timestamp", datetime.now().isoformat())

    pdf = ReportPDF(title=title, orientation="L", format="A4")
    pdf.alias_nb_pages()
    pdf.add_page()

    # Title block
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*HEADER_BG)
    pdf.cell(0, 12, _safe(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Generated: {scan_ts}", new_x="LMARGIN", new_y="NEXT")

    total_banners = len(banners)
    all_pass = all(
        all(c.get("status") != "FAIL" for c in b.get("checks", []))
        for b in banners
    )
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    if all_pass:
        pdf.set_text_color(*COLORS["PASS"])
        pdf.cell(0, 7, f"All {total_banners} banner(s) passed compliance checks.",
                 new_x="LMARGIN", new_y="NEXT")
    else:
        fail_count = sum(1 for b in banners
                         if any(c.get("status") == "FAIL" for c in b.get("checks", [])))
        pdf.set_text_color(*COLORS["FAIL"])
        pdf.cell(0, 7, f"{fail_count} of {total_banners} banner(s) have compliance issues.",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Summary table
    pdf.summary_table(banners)

    # Detail sections
    for banner in banners:
        pdf.add_page()
        pdf.banner_detail(banner)

    # Fix suggestions
    pdf.fix_suggestions(banners)

    pdf.output(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="HTML5 Spec Guard — PDF Report Generator")
    parser.add_argument("--input", "-i", help="Path to JSON results file (default: stdin)")
    parser.add_argument("--output", "-o", required=True, help="Output PDF path")

    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    out = generate_report(data, args.output)
    print(f"Report generated: {out}")


if __name__ == "__main__":
    main()
