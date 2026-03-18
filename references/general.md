# General Checks — All Platforms

These checks apply to every platform and use the `GEN-` prefix.

---

### GEN-PERF-01: Chrome Heavy Ad Threshold
- **Rule:** Total uncompressed asset size should not exceed 4 MB (4,194,304 bytes)
- **Rationale:** Chrome's Heavy Ad Intervention blocks ads exceeding this threshold
- **Severity:** WARNING

### GEN-PERF-02: Chrome Heavy Ad CPU Threshold
- **Rule:** CPU usage should not exceed 15 seconds in any 30-second window
- **Rationale:** Chrome's Heavy Ad Intervention unloads ads exceeding this threshold
- **Detection:** Requires `--runtime` flag. Launches headless Chromium, measures CDP TaskDuration over 30s.
- **Severity:** WARNING
- **Note:** Adds ~30s per banner. Also extrapolates toward 60s total CPU limit.

### GEN-PKG-06: Zero-Byte Files
- **Rule:** Archive should not contain zero-byte (empty) files
- **Detection:** Check `file_size == 0` for all entries
- **Severity:** WARNING

### GEN-PKG-07: Junk Files
- **Rule:** Archive should not contain OS junk files or VCS artifacts
- **Detection:** Flag `.DS_Store`, `Thumbs.db`, `desktop.ini`, `.gitkeep`, `__MACOSX/` directories, `.git/` directories
- **Severity:** WARNING

### GEN-HTML-03: Viewport Meta Tag (Mobile)
- **Rule:** Mobile ads (declared width ≤ 320px) should include a viewport meta tag
- **Pattern:** `<meta name="viewport" content="width=device-width, initial-scale=1">`
- **Applies when:** Ad size meta tag declares width ≤ 320
- **Severity:** WARNING

### GEN-JS-01: Debug Statements
- **Rule:** Production ads should not contain debug statements
- **Detection:** Search for `console.log()`, `console.warn()`, `console.error()`, `console.debug()`, `console.info()`, and `debugger` statements in JS files and inline scripts
- **Severity:** WARNING

### GEN-JS-02: Bundled Libraries
- **Rule:** Common JS libraries should be loaded from CDN rather than bundled in the archive
- **Detection:** Checks for GSAP, jQuery, anime.js, and CreateJS by filename and code signatures
- **Suggestion:** Load from CDN to reduce package size
- **Severity:** WARNING

### GEN-SEC-03: External Domain Allowlist
- **Rule:** External domains referenced in ad code should be on the approved ad-tech domain list
- **Approved domains:** google.com, doubleclick.net, 2mdn.net, googlesyndication.com, googletagmanager.com, googletagservices.com, google-analytics.com, googleapis.com, gstatic.com, cdnjs.cloudflare.com, cdn.jsdelivr.net, www.w3.org, adform.net, adform.com, s1.adform.net, adkit-advertising.amazon (and all subdomains)
- **Severity:** WARNING

---

## Common Ad Sizes (Reference)

| Size | Description |
|------|-------------|
| 300×250 | Medium Rectangle |
| 728×90 | Leaderboard |
| 160×600 | Wide Skyscraper |
| 320×50 | Mobile Leaderboard |
| 300×600 | Half Page |
| 970×250 | Billboard |
| 970×90 | Large Leaderboard |
| 320×100 | Large Mobile Banner |
| 336×280 | Large Rectangle |
| 468×60 | Full Banner |
