---
name: html5-spec-guard
description: Validates HTML5 banner ad ZIP files against advertising platform specifications (CM360, DV360, TTD, Adform, Amazon DSP). Scans banners, runs compliance checks, generates PDF reports, and manages file archival. Use when users want to validate, scan, or check HTML5 banner ads for platform compliance, ask about ad spec requirements, or say things like "check my banners", "are these ads compliant?", "spec check", or "validate ads".
---

# HTML5 Spec Guard — Skill Workflow

You validate HTML5 banner ad ZIP files against advertising platform specifications. Follow this workflow precisely.

## Step 1: Ensure dependencies and workspace directories

### Dependencies

Check which optional Python packages are available by running:

```bash
python3 -c "import fpdf" 2>/dev/null && echo "fpdf2: installed" || echo "fpdf2: missing"
python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null && echo "playwright: installed" || echo "playwright: missing"
```

Based on the results, present the user with relevant install options:

- **If both are missing**, offer:
  1. Install both (`pip install fpdf2 playwright && playwright install chromium`)
  2. Install fpdf2 only (`pip install fpdf2`) — PDF reports available, no CPU check
  3. Install playwright only (`pip install playwright && playwright install chromium`) — CPU check available, results in CLI/chat only
  4. Skip — continue without either (static checks only, results in CLI/chat only)

- **If only fpdf2 is missing**, offer:
  1. Install fpdf2 (`pip install fpdf2`) — enables PDF reports
  2. Skip — continue without PDF reports (results in CLI/chat only)

- **If only playwright is missing**, offer:
  1. Install playwright (`pip install playwright && playwright install chromium`) — enables CPU check
  2. Skip — continue without CPU check (static checks only)

- **If both are installed**, proceed silently.

After resolving dependencies, carry forward what is available — this affects later steps:
- If fpdf2 is **not** available: omit the `--pdf` flag in Step 5, show results in CLI/chat output only
- If playwright is **not** available: skip Step 4 entirely (no CPU check prompt) and omit `--runtime` in Step 5

### Workspace directories

Make sure these directories exist in the current working directory:
- `scan/` — where the user drops ZIP files for checking
- `output/` — where PDF reports are generated (only needed if fpdf2 is available)
- `archive/` — where processed ZIPs are moved after scanning

Create any missing directories silently using `mkdir -p`.

## Step 2: List ZIPs in scan/

List all `.zip` and `.adz` files in `scan/`. If none are found, tell the user to place their HTML5 banner ZIP files in the `scan/` folder and stop.

## Step 3: Determine target platform

Ask the user which platform spec to check against. Present as a numbered list:

1. **CM360** — Campaign Manager 360
2. **DV360** — Display & Video 360
3. **TTD** — The Trade Desk
4. **Adform** — Adform DSP/Ad Server
5. **Amazon DSP** — Amazon Demand-Side Platform
6. **Both** — CM360 + DV360
7. **All** — CM360 + DV360 + TTD + Adform + Amazon DSP

If only one platform is relevant based on conversation context, you may skip this prompt.

## Step 4: Runtime CPU check

If playwright is not available (user skipped install in Step 1), skip this step entirely — `--runtime` cannot be used.

Ask the user whether to include the Playwright CPU measurement:

1. **Yes** — include `--runtime` (~30s extra per banner, adds GEN-PERF-02)
2. **No** — static checks only (faster)

If the user passed an explicit flag in conversation context (e.g. `/html5-spec-guard --runtime`), skip this prompt.

## Step 5: Scan and generate report

If fpdf2 is not available (user skipped install in Step 1), omit the `--pdf` flag below and present the check results as a formatted summary in the CLI/chat output instead.

Run the scanner with the chosen platform(s). It reads ZIPs in-memory, runs all checks, and generates the PDF directly:

```bash
python3 ~/.claude/skills/html5-spec-guard/scripts/scan_banners.py \
  --scan-dir scan/ \
  --platforms cm360,dv360,ttd,adform,amazondsp \
  --runtime \          # ← include only if user chose Yes in Step 4
  --exit-code \        # ← optional: exit 1 if any FAIL (for CI/CD)
  --allow-domain cdn.example.com \  # ← optional: add trusted domains (repeatable)
  --pdf "output/html5-compliance-report_YYYYMMDD-HHMMSS.pdf"
```

Use the current timestamp for the filename. Tell the user where the PDF was saved and give a brief summary.

The check IDs and rules are documented in platform-specific reference files (`references/cm360.md`, `references/dv360.md`, `references/ttd.md`, `references/adform.md`, `references/amazondsp.md`) and shared general checks in `references/general.md`. The scanner (`scripts/scan_banners.py`) implements all checks and calls `scripts/generate_report.py` for PDF output.

## Step 6: Archive prompt

Ask the user what to do with the scanned ZIP files:

1. **Archive** — move to `archive/YYYYMMDD-HHMMSS/` (create timestamped subfolder)
2. **Delete** — remove from `scan/`
3. **Leave** — keep in `scan/` as-is

If the user chooses **Archive**, ask a follow-up:

   a. **All banners** — archive every scanned ZIP regardless of check results
   b. **Only passed** — archive only ZIPs where all checks passed (no FAILs); ZIPs with any FAIL stay in `scan/` for re-checking after fixes

Execute the chosen action. When archiving "only passed", tell the user which ZIPs remained in `scan/` and why.

---

## Important notes

- Always use check IDs from the reference files (e.g., CM360-PKG-01, DV360-FILE-01, TTD-CLICK-01) in all output — both terminal and PDF reports
- Heuristic checks (animation duration, polite load detection) should be marked as WARNING, never FAIL
- When checking both platforms, run all checks from both specs and clearly label which platform each check belongs to
- If a ZIP is actually an `.adz` file, treat it identically to `.zip` (CM360 accepts both)
- Auto-detect rich media: if any file references `Enabler.js`, switch from clickTag checks to Enabler exit event checks
- The PDF report is one file per scan session — all banners in a single report with a summary table followed by per-banner detail sections
