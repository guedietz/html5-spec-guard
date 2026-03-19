# HTML5 Spec Guard

**Validate HTML5 banner ad ZIPs against ad platform specs — before trafficking.**

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platforms: Windows | macOS | Linux](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

---

## What It Does

HTML5 Spec Guard scans HTML5 banner ZIP files against the official ad specifications for **CM360**, **DV360**, **The Trade Desk**, **Adform**, and **Amazon DSP**. It runs 80+ automated checks covering package structure, file types, click tracking, security, performance, polite loading, animation limits, and audio/video rules. Results are output as styled **PDF reports** and/or **JSON** for CI/CD integration, with optional runtime CPU and JS heap profiling via headless Chromium.

---

## Quick Start

### A) Standalone CLI (no Claude Code needed)

```bash
git clone https://github.com/your-org/html5-spec-guard.git
cd html5-spec-guard

# Install optional dependencies
pip install -r requirements.txt
playwright install chromium

# Create directories
mkdir scan output

# Drop your banner ZIPs into scan/
# Then run:
python scripts/scan_banners.py --scan-dir scan/ --platforms all --pdf output/report.pdf
```

### B) As a Claude Code Skill

```bash
# Copy the skill directory to ~/.claude/skills/html5-spec-guard/
# Then in any project directory, run:
/html5-spec-guard
```

The skill will walk you through platform selection, optional runtime checks, and report generation interactively.

---

## Supported Platforms

| Platform | Click Mechanism | Max Size | Key Limits |
|---|---|---|---|
| **CM360** | `clickTag` variable | 10 MB | 100 files, `.zip`/`.adz` |
| **DV360** | `clickTag` or `Enabler.exit()` | 5 MB | 100 files, 50-char AV filenames |
| **The Trade Desk** | `clickTAG` (uppercase) | 10 MB compressed / 12 MB uncompressed | 100 KB max HTML, 2.2 MB per file |
| **Adform** | `dhtml.getVar('clickTAG')` | 300 KB | `manifest.json` required, `Adform.DHTML.js` required |
| **Amazon DSP** | `SDK.clickThrough()` | 200 KB | `index.html` required, external JS from Amazon CDN only |

---

## CLI Reference

```
python scripts/scan_banners.py [OPTIONS]
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--scan-dir` | path | `scan` | Directory containing ZIP files to scan |
| `--platforms` | string | `cm360,dv360` | Comma-separated list: `cm360`, `dv360`, `ttd`, `adform`, `amazondsp`, `both` (cm360+dv360), or `all` |
| `--pdf` | path | — | Generate a PDF report at this path |
| `--json` | flag | — | Output JSON results to stdout |
| `--runtime` | flag | — | Run CPU & memory measurement via Playwright (~30s per banner) |
| `--exit-code` | flag | — | Exit with code 1 if any check FAILs (for CI/CD) |
| `--allow-domain` | string | — | Additional trusted domain for GEN-SEC-03 (repeatable) |

### Usage Examples

```bash
# Scan for CM360 + DV360 (default), output PDF
python scripts/scan_banners.py --pdf report.pdf

# Scan for all platforms with JSON output
python scripts/scan_banners.py --platforms all --json > results.json

# CI mode: fail the build if any check fails
python scripts/scan_banners.py --platforms cm360 --exit-code

# Include runtime performance checks
python scripts/scan_banners.py --platforms dv360 --runtime --pdf report.pdf

# Allow a custom CDN domain
python scripts/scan_banners.py --allow-domain cdn.example.com --allow-domain assets.example.com
```

---

## Check Reference

Every check has a unique ID, a severity level (**FAIL**, **WARNING**, or **INFO**), and a human-readable message. FAIL-level checks indicate spec violations that will cause rejection. WARNING-level checks flag best-practice issues. INFO checks are informational only.

### General Checks (all platforms)

| Check ID | Severity | Rule |
|---|---|---|
| GEN-PERF-01 | WARNING | Total uncompressed size ≤ 4 MB (Chrome Heavy Ad threshold) |
| GEN-PERF-02 | WARNING | CPU time ≤ 15s in any 30s window (requires `--runtime`) |
| GEN-PERF-03 | WARNING | Peak JS heap ≤ 50 MB (requires `--runtime`) |
| GEN-PKG-06 | WARNING | No zero-byte (empty) files |
| GEN-PKG-07 | WARNING | No OS junk files (`.DS_Store`, `Thumbs.db`, `__MACOSX/`, etc.) |
| GEN-HTML-03 | WARNING | Mobile ads (width ≤ 320px) should include viewport meta tag |
| GEN-JS-01 | WARNING | No debug statements (`console.log`, `debugger`, etc.) |
| GEN-JS-02 | WARNING | Common libraries (GSAP, jQuery, anime.js, CreateJS) should load from CDN |
| GEN-SEC-03 | WARNING | External domains must be on the approved list (extensible via `--allow-domain`) |

### Per-Platform Check Categories

Each platform has checks in these categories. See `references/*.md` for the full specification per platform.

| Category | Check ID Pattern | Example Checks |
|---|---|---|
| Package | `*-PKG-*` | Archive format, file count, size limits |
| File | `*-FILE-*` | Allowed extensions, no nested ZIPs |
| HTML | `*-HTML-*` | `ad.size` meta tag, valid structure |
| Click | `*-CLICK-*` | Click variable defined, not hardcoded |
| Animation | `*-ANIM-*` | Duration limits, no infinite loops |
| Audio/Video | `*-AV-*` | No autoplay, muted attribute required |
| Polite Load | `*-POLITE-*` | Initial load thresholds, polite loading detection |
| Security | `*-SEC-*` | HTTPS-only URLs, no localStorage |
| Rich Media | `DV360-RICH-*` | Enabler.js detection, `Enabler.exit()` usage |
| DHTML | `ADFORM-DHTML-*` | `Adform.DHTML.js` reference required |

For the full specification per platform, see the reference files in `references/`.

---

## PDF Report

When you pass `--pdf`, the scanner generates a landscape A4 PDF report containing:

1. **Title block** — report name, generation timestamp, overall pass/fail summary
2. **Summary table** — one row per banner with pass/fail/warning/info counts at a glance
3. **Detail sections** — per-banner breakdown with metadata (declared size, file count, total KB, click variables) and every check result color-coded:
   - Green = PASS
   - Red = FAIL
   - Amber = WARNING
   - Blue = INFO
4. **Fix suggestions** — actionable recommendations grouped by platform, with deduplicated general checks

---

## Runtime Performance Checks

The `--runtime` flag enables two additional checks powered by headless Chromium:

| Check | Threshold | What It Measures |
|---|---|---|
| **GEN-PERF-02** | 15 seconds CPU in a 30-second window | Chrome Heavy Ad Intervention CPU limit |
| **GEN-PERF-03** | 50 MB peak JS heap | Memory pressure on low-end devices |

**How it works:**
1. Extracts the banner ZIP to a temp directory
2. Starts a local HTTP server
3. Launches headless Chromium via Playwright
4. Reads the ad size from the HTML meta tag (defaults to 300x250)
5. Uses Chrome DevTools Protocol (CDP) to record `TaskDuration` and sample `JSHeapUsedSize` every 2 seconds over a 30-second window
6. Reports whether thresholds are exceeded

**Requires:** `pip install playwright && playwright install chromium`

**Timing:** ~30 seconds per banner.

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Banner Compliance

on:
  push:
    paths: ['banners/**/*.zip']
  pull_request:
    paths: ['banners/**/*.zip']

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install fpdf2

      - name: Run HTML5 Spec Guard
        run: |
          python scripts/scan_banners.py \
            --scan-dir banners/ \
            --platforms all \
            --json > results.json \
            --exit-code

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: compliance-results
          path: results.json
```

The `--exit-code` flag causes the scanner to exit with code 1 if any FAIL-level check is triggered, which fails the CI job.

---

## JSON Output Schema

When using `--json`, results are written to stdout in this structure:

```json
{
  "title": "HTML5 Banner Compliance Report",
  "scan_timestamp": "2026-03-18T09:30:45",
  "banners": [
    {
      "filename": "my_banner_300x250.zip",
      "platform": "CM360",
      "metadata": {
        "declared_size": "300x250",
        "file_count": 15,
        "total_size_kb": 450.5,
        "initial_load_kb": 125.3,
        "is_rich_media": false,
        "clicktag_vars": ["clickTag"]
      },
      "checks": [
        {
          "id": "CM360-PKG-01",
          "status": "PASS",
          "message": "Archive format valid (.zip)",
          "suggestion": null
        },
        {
          "id": "CM360-CLICK-02",
          "status": "FAIL",
          "message": "clickTag hardcoded to a URL",
          "suggestion": "Use URL parameters or placeholder values instead."
        }
      ]
    }
  ]
}
```

| Field | Description |
|---|---|
| `id` | Unique check identifier (e.g. `CM360-PKG-01`, `GEN-PERF-02`) |
| `status` | `PASS`, `FAIL`, `WARNING`, or `INFO` |
| `message` | Human-readable result description |
| `suggestion` | Fix recommendation (present on `FAIL` results, `null` otherwise) |

---

## Project Structure

```
html5-spec-guard/
├── README.md
├── requirements.txt          # Optional dependencies (fpdf2, playwright)
├── SKILL.md                  # Claude Code skill definition & workflow
├── .gitignore
├── references/               # Full platform spec documentation
│   ├── general.md            # Shared checks (GEN-*)
│   ├── cm360.md              # Campaign Manager 360
│   ├── dv360.md              # Display & Video 360
│   ├── ttd.md                # The Trade Desk
│   ├── adform.md             # Adform DSP/Ad Server
│   └── amazondsp.md          # Amazon Demand-Side Platform
└── scripts/                  # Python implementation
    ├── scan_banners.py       # Main scanner (CLI entry point)
    ├── generate_report.py    # PDF report generator
    └── runtime_checks.py     # Headless Chromium CPU/memory profiler
```

---

## Dependencies

| Dependency | Required? | Purpose |
|---|---|---|
| **Python 3.9+** | Yes | Core scanner uses standard library only |
| **fpdf2** | Optional | PDF report generation |
| **Playwright** | Optional | Runtime CPU/memory checks |

Install optional dependencies: `pip install -r requirements.txt && playwright install chromium`

---

## Contributing

Contributions are welcome! Areas where help is appreciated:

- Additional platform specs
- Improved animation duration detection heuristics
- Rich media framework support beyond Enabler.js
- Better minification-aware click tracking detection

Please open an issue to discuss before submitting large changes.

---

## Author

**Günther Dietz**
Head of Business Development & Programmatic @ otago Online Consulting 🇦🇹
(Vibe coded with Claude Code)

Building transparency & automation tools for the open web.

💼 [LinkedIn](https://linkedin.com/in/dietzguenther/) • 🧠 [GitHub](https://github.com/guedietz)

---

## License

MIT License. See [LICENSE](LICENSE) for details.
