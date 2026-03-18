# The Trade Desk (TTD) — HTML5 Banner Specifications

Reference for automated compliance checks. Each check has a unique ID for traceability in reports.

---

## Package Requirements

### TTD-PKG-01: Archive Format
- **Allowed formats:** `.zip`
- **Severity:** FAIL

### TTD-PKG-02: Maximum File Count
- **Limit:** 100 files per archive
- **Severity:** FAIL

### TTD-PKG-03: Maximum Package Size (Compressed)
- **Limit:** 10 MB (10,485,760 bytes)
- **Severity:** FAIL

### TTD-PKG-04: Maximum Uncompressed Size
- **Limit:** 12 MB (12,582,912 bytes)
- **Severity:** FAIL

### TTD-PKG-05: Primary HTML File
- **Rule:** Archive must contain at least one `.html` or `.htm` file at the root level
- **Severity:** FAIL (no HTML found, or HTML in deep nested path) /
  WARNING (HTML inside a single wrapper folder — macOS Archive Utility pattern)

---

## File Requirements

### TTD-FILE-01: Allowed File Types
- **Allowed extensions:** `.html`, `.htm`, `.js`, `.css`, `.mp4`, `.jpg`, `.jpeg`, `.gif`, `.png`, `.svg`
- **Severity:** FAIL
- **Note:** No font files allowed in package (use CDN-hosted fonts instead)

### TTD-FILE-02: No Nested ZIP Archives
- **Rule:** Archive must not contain nested `.zip` files
- **Severity:** FAIL

### TTD-FILE-03: Primary HTML File Size
- **Limit:** 100 KB (102,400 bytes)
- **Severity:** FAIL

### TTD-FILE-04: Individual File Size
- **Limit:** 2.2 MB (2,306,867 bytes) per file
- **Severity:** FAIL

---

## HTML Requirements

### TTD-HTML-01: Ad Size Meta Tag
- **Rule:** Primary HTML file should contain a `<meta>` tag declaring the ad dimensions
- **Pattern:** `<meta name="ad.size" content="width=X,height=Y"/>`
- **Validation:** `X` and `Y` must be positive integers
- **Severity:** FAIL

### TTD-HTML-02: Valid HTML Structure
- **Rule:** Primary HTML file must contain `<!DOCTYPE html>`, `<html>`, `<head>`, and `<body>` tags
- **Severity:** WARNING

---

## Click Tracking

### TTD-CLICK-01: clickTAG Variable Present
- **Rule:** The JavaScript code must define a `clickTAG` variable (case-sensitive — uppercase TAG)
- **Patterns to search:**
  - `var clickTAG` / `let clickTAG` / `const clickTAG`
  - `window.clickTAG`
  - `getParameterByName("clickTAG")`
- **Note:** TTD uses `clickTAG` (uppercase TAG), not `clickTag` like CM360/DV360
- **Severity:** FAIL

### TTD-CLICK-02: clickTAG Not Hardcoded
- **Rule:** The `clickTAG` value must not be a hardcoded URL
- **Patterns that FAIL:**
  - `clickTAG = "http://..."` or `clickTAG = 'http://...'`
  - `clickTAG = "https://..."` or `clickTAG = 'https://...'`
- **Acceptable patterns:**
  - Assignment from `getParameterByName("clickTAG")`
  - Assignment from URL parameters
  - Placeholder values like `""` or `''`
- **Severity:** FAIL (clickTAG hardcoded to a URL) / INFO (clickTAG not found — N/A)

---

## Security

### TTD-SEC-01: HTTPS Only
- **Rule:** All URLs referenced in HTML, JS, and CSS files must use `https://` protocol (SSL compliant)
- **Detection:** Search for `http://` URLs (excluding `http://www.w3.org` namespace references)
- **Severity:** FAIL (HTTP URL to an untrusted domain) /
  WARNING (HTTP URL to a known-trusted domain — still should be upgraded to HTTPS)

### TTD-SEC-02: No Local Storage
- **Rule:** Code must not use `localStorage` or `sessionStorage`
- **Patterns to search:** `localStorage`, `sessionStorage`
- **Severity:** FAIL

---

## Animation

### TTD-ANIM-01: Maximum Animation Duration
- **Limit:** 15 seconds — animation must loop for max 15 seconds, then stop (static)
- **Detection heuristics:**
  - Check CSS `animation-duration` values
  - Check `setTimeout` / `setInterval` with values > 15000 ms
- **Severity:** WARNING
- **Note:** Heuristic check — cannot guarantee accurate detection of total animation duration

---

## Polite Loading

### TTD-POLITE-01: Polite Load / Initial Load Limit
- **Rule:** Initial load should not exceed 300 KB (307,200 bytes); 200 KB recommended
- **Subload limit:** 600 KB
- **Initial file load count:** Max 10 files
- **Detection:** Estimate initial payload from `<head>` and pre-polite `<body>` references; check for polite load patterns
- **Severity:** WARNING
- **Note:** Heuristic check — cannot guarantee correctness

---

General checks (GEN-*) and common ad sizes are in [general.md](general.md).
