---
name: 🐛 Bug Report / Edge Case
about: Report a validation error or a missed platform specification.
title: "[BUG] <Brief description of the issue>"
labels: bug, needs-triage
---

### 🔍 Discovery Details
* **Target Platform:** (e.g., TTD, Amazon DSP, Adform)
* **Check ID involved:** (e.g., AMAZONDSP-JS-01, TTD-CLICK-01)
* **Banner Dimensions:** (e.g., 300x250)

### 🚩 The Issue
* **What happened?** (e.g., The tool marked a valid TTD clickTAG as FAIL).
* **What was expected?** (e.g., It should pass because the variable was defined in an external JS file).

### 🛠️ Reproduction Steps
1. Place the problematic ZIP in the `/scan` folder.
2. Run command: `python3 scripts/scan_banners.py --platforms <platform> --runtime`.
3. Review the JSON/PDF output.

### 💻 Environment Info
* **Python Version:** (e.g., 3.11)
* **Playwright Status:** (Installed / Not Installed)
* **OS:** (Windows / Mac / Linux)

### 📂 Supporting Files
*Please provide the JSON output or a redacted version of the HTML/JS code triggering the issue if possible.*
