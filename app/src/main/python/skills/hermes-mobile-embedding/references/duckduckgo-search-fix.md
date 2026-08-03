# DuckDuckGo Search Fix (Node.js vs curl)

## Problem
Node.js v18's native `fetch()` on GCP gets a SHORTER, different HTML response from DuckDuckGo Lite than curl does — no `result-link` class elements, so search returns empty results.

## Root Cause
Node.js v18 fetch sends different HTTP headers (e.g. `Accept-Encoding`, `Sec-Fetch-*`) causing DDG to serve a simplified landing page instead of the full results page.

## Fix
Use `child_process.execSync('curl ...')` instead of `fetch()`:

```javascript
const { execSync } = require('child_process');
const curlCmd = `curl -sL 'https://lite.duckduckgo.com/lite/' -H 'User-Agent: Mozilla/5.0' -X POST -d 'q=${encodeURIComponent(query)}'`;
const html = execSync(curlCmd, { timeout: 15000, maxBuffer: 1024 * 1024 }).toString();
```

Alternative: Parse HTML with regex instead of htmlparser2 (which may have quote-style issues):
```javascript
const linkRe = /<a[^>]+rel=['"]nofollow['"][^>]+href=['"]([^'"]+)['"][^>]*class=['"]result-link['"][^>]*>([^<]+)<\/a>/gi;
const snipRe = /<td class=['"]result-snippet['"]>([\s\S]*?)<\/td>/gi;
```

For Python engine (mobile): Use `urllib.request` with `User-Agent: Mozilla/5.0` header — works fine because Python's HTTP client sends compatible headers.

## ⚠️ Android UA trap (found 2026-08, live-tested)

DDG serves a **stripped page with ZERO `result-link` elements** for mobile-ish UAs. The exact UA matters:

| User-Agent | Page size | result-link count |
|------------|-----------|-------------------|
| `Mozilla/5.0` (plain) | 24666 B | 10 ✅ |
| `Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/120` | 24666 B | 10 ✅ |
| `Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36` | 14246 B | **0 ❌** |

A previous "improvement" set the Android UA in `hermes_agent.py` (`web_search`) thinking a phone app should send a phone UA — it silently broke search (empty `[]` results, no error). **Fix: use a desktop/plain UA in `web_search`**, never `Linux; Android ...`. Add a comment at the call site explaining why, so nobody "helpfully" reverts it.

Quick regression probe (no server needed):
```python
import urllib.request, urllib.parse, re
req = urllib.request.Request(
    f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote('test')}",
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
)
html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
print(len(re.findall(r'<a[^>]+class=["\']?result-link["\']?[^>]*>([^<]+)</a>', html)))
# expect >= 5; 0 means UA stripped the page again
```

Related regex note: the class attr is now `class='result-link'` (single quotes) — the pattern `class=["\']?result-link["\']?` tolerates both quote styles.
