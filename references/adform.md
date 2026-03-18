# Adform — HTML5 Banner Specifications

Reference for automated compliance checks. Each check has a unique ID for traceability in reports.

---

## Package Requirements

### ADFORM-PKG-01: Archive Format
- **Allowed formats:** `.zip`
- **Severity:** FAIL

### ADFORM-PKG-02: manifest.json Present
- **Rule:** Archive must contain a `manifest.json` file at the ZIP root
- **Severity:** FAIL

### ADFORM-PKG-03: manifest.json Valid
- **Rule:** `manifest.json` must parse as valid JSON and contain required fields: `version`, `title`, `width`, `height`, `source`
- **Severity:** FAIL

### ADFORM-PKG-04: Source File Present
- **Rule:** The HTML file specified in the manifest.json `source` field must exist at the ZIP root
- **Severity:** FAIL

### ADFORM-PKG-05: Maximum Package Size
- **Limit:** 300 KB (307,200 bytes)
- **Severity:** FAIL

---

## File Requirements

### ADFORM-FILE-01: Allowed File Types
- **Allowed extensions:** `.html`, `.htm`, `.js`, `.css`, `.jpg`, `.jpeg`, `.gif`, `.png`, `.svg`, `.json`, `.xml`, `.eot`, `.otf`, `.ttf`, `.woff`, `.woff2`, `.mp4`, `.webm`
- **Severity:** FAIL
- **Note:** Files without extensions or with disallowed extensions must be flagged

### ADFORM-FILE-02: No Nested ZIP Archives
- **Rule:** Archive must not contain nested `.zip` files
- **Severity:** FAIL

---

## HTML Requirements

### ADFORM-HTML-01: Ad Size from manifest.json
- **Rule:** Ad dimensions are read from the `width` and `height` fields in `manifest.json`. Both must be valid positive integers. Falls back to `<meta name="ad.size">` if manifest fields are missing.
- **Severity:** FAIL

### ADFORM-HTML-02: Valid HTML Structure
- **Rule:** Primary HTML file must contain `<!DOCTYPE html>`, `<html>`, `<head>`, and `<body>` tags
- **Severity:** WARNING

---

## DHTML Library

### ADFORM-DHTML-01: DHTML Library Reference
- **Rule:** HTML must reference `Adform.DHTML.js` (loaded via `<script>` tag or `document.write`)
- **Pattern:** `Adform.DHTML.js` in ad code
- **Severity:** FAIL

---

## Click Tracking

### ADFORM-CLICK-01: clickTAG Implementation
- **Rule:** Must use `dhtml.getVar('clickTAG')` pattern to retrieve clickTAG value from the Adform DHTML API
- **Pattern:** `dhtml.getVar('clickTAG'` or `dhtml.getVar("clickTAG"`
- **Also detects:** `clickTAG2`, `clickTAG3`, etc.
- **Severity:** FAIL

### ADFORM-CLICK-02: clickTAG in manifest.json
- **Rule:** The `clicktags` section in `manifest.json` should declare at least `clickTAG`
- **Severity:** WARNING

---

## Animation

### ADFORM-ANIM-01: Maximum Animation Duration
- **Limit:** 30 seconds
- **Detection heuristics:**
  - Check CSS `animation-duration` values
  - Check `setTimeout` / `setInterval` with values > 30000 ms
- **Severity:** WARNING
- **Note:** Heuristic check — cannot guarantee accurate detection of total animation duration

### ADFORM-ANIM-02: Animation Looping
- **Rule:** Animations should not loop indefinitely
- **Detection:** Check for `animation-iteration-count: infinite` in CSS
- **Severity:** WARNING

---

## Audio & Video

### ADFORM-AV-01: No Autoplay Audio
- **Rule:** Audio must not autoplay
- **Detection:** Search for `<audio` tags with `autoplay` attribute, or `new Audio()` with immediate `.play()`
- **Severity:** FAIL

### ADFORM-AV-02: Video Must Be Muted
- **Rule:** If video elements exist, they must include the `muted` attribute
- **Detection:** Search for `<video` tags without `muted` attribute
- **Severity:** FAIL

---

## Security

### ADFORM-SEC-01: HTTPS Only
- **Rule:** All URLs referenced in HTML, JS, and CSS files must use `https://` protocol
- **Detection:** Search for `http://` URLs (excluding `http://www.w3.org` namespace references)
- **Severity:** FAIL (HTTP URL to an untrusted domain) /
  WARNING (HTTP URL to a known-trusted domain — still should be upgraded to HTTPS)

### ADFORM-SEC-02: No Local Storage
- **Rule:** Code must not use `localStorage` or `sessionStorage`
- **Patterns to search:** `localStorage`, `sessionStorage`
- **Severity:** FAIL

---

## Polite Loading

### ADFORM-POLITE-01: Polite Load Threshold
- **Rule:** If total uncompressed asset size exceeds 150 KB (153,600 bytes), the banner should implement polite loading
- **Detection:** Check for polite load patterns:
  - `window.addEventListener("load", ...)`
  - `document.addEventListener("DOMContentLoaded", ...)`
- **Severity:** WARNING
- **Note:** Heuristic check — cannot guarantee correctness

### ADFORM-POLITE-02: Initial Load Image Size
- **Rule:** If polite loading is needed, individual images should be under 40 KB for initial load
- **Severity:** WARNING

---

General checks (GEN-*) and common ad sizes are in [general.md](general.md).
