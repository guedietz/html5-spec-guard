# Amazon DSP — HTML5 Banner Specifications

Reference for automated compliance checks. Each check has a unique ID for traceability in reports.

---

## Package Requirements

### AMAZONDSP-PKG-01: Archive Format
- **Allowed formats:** `.zip`
- **Severity:** FAIL

### AMAZONDSP-PKG-02: Maximum Package Size
- **Limit:** 200 KB (204,800 bytes)
- **Severity:** FAIL

### AMAZONDSP-PKG-03: index.html at Root
- **Rule:** Archive must contain `index.html` at the ZIP root
- **Severity:** FAIL

---

## File Requirements

### AMAZONDSP-FILE-01: Allowed File Types
- **Allowed extensions:** `.html`, `.htm`, `.js`, `.css`, `.jpg`, `.jpeg`, `.png`, `.gif`, `.woff`, `.eot`, `.json`
- **Severity:** FAIL
- **Note:** Files without extensions or with disallowed extensions must be flagged

### AMAZONDSP-FILE-02: No Nested ZIP Archives
- **Rule:** Archive must not contain nested `.zip` files
- **Severity:** FAIL

---

## HTML Requirements

### AMAZONDSP-HTML-01: Ad Size Meta Tag
- **Rule:** Primary HTML must contain `<meta name="ad.size" content="width=X,height=Y">`
- **Severity:** FAIL

### AMAZONDSP-HTML-02: Valid HTML Structure
- **Rule:** Primary HTML file must contain `<!DOCTYPE html>`, `<html>`, `<head>`, and `<body>` tags
- **Severity:** WARNING

---

## Click Tracking

### AMAZONDSP-CLICK-01: SDK.clickThrough() Implementation
- **Rule:** Must use `SDK.clickThrough()` for click tracking
- **Pattern:** `SDK.clickThrough(` in ad code
- **Severity:** FAIL

---

## JavaScript

### AMAZONDSP-JS-01: Restricted External Scripts
- **Rule:** No external `<script src="...">` except from `adkit-advertising.amazon` domains
- **Detection:** Scan all `<script src="...">` tags for domains not matching `adkit-advertising.amazon`
- **Severity:** FAIL

---

## Animation

### AMAZONDSP-ANIM-01: Maximum Animation Duration
- **Limit:** 15 seconds
- **Detection heuristics:**
  - Check CSS `animation-duration` values
  - Check `setTimeout` / `setInterval` with values > 15000 ms
- **Severity:** WARNING
- **Note:** Heuristic check — cannot guarantee accurate detection of total animation duration

### AMAZONDSP-ANIM-02: Animation Looping
- **Rule:** Maximum 3 loops; no `infinite` looping
- **Detection:** Check for `animation-iteration-count: infinite` or values > 3 in CSS
- **Severity:** WARNING

---

## Audio & Video

### AMAZONDSP-AV-01: No Autoplay Audio
- **Rule:** Audio must not autoplay
- **Detection:** Search for `<audio` tags with `autoplay` attribute, or `new Audio()` with immediate `.play()`
- **Severity:** FAIL

### AMAZONDSP-AV-02: Video Must Be Muted
- **Rule:** If video elements exist, they must include the `muted` attribute
- **Detection:** Search for `<video` tags without `muted` attribute
- **Severity:** FAIL

---

## Security

### AMAZONDSP-SEC-01: HTTPS Only
- **Rule:** All URLs referenced in HTML, JS, and CSS files must use `https://` protocol
- **Detection:** Search for `http://` URLs (excluding `http://www.w3.org` namespace references)
- **Severity:** FAIL

### AMAZONDSP-SEC-02: No Local Storage
- **Rule:** Code must not use `localStorage` or `sessionStorage`
- **Patterns to search:** `localStorage`, `sessionStorage`
- **Severity:** FAIL

---

## Polite Loading

### AMAZONDSP-POLITE-01: Polite Load Threshold
- **Rule:** If total uncompressed asset size exceeds 150 KB (153,600 bytes), the banner should implement polite loading
- **Detection:** Check for polite load patterns:
  - `window.addEventListener("load", ...)`
  - `document.addEventListener("DOMContentLoaded", ...)`
- **Severity:** WARNING
- **Note:** Heuristic check — cannot guarantee correctness

### AMAZONDSP-POLITE-02: Initial Load Image Size
- **Rule:** If polite loading is needed, individual images should be under 40 KB for initial load
- **Severity:** WARNING

---

General checks (GEN-*) and common ad sizes are in [general.md](general.md).
