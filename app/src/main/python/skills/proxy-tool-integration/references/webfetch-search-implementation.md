# Web Search & Fetch Endpoint Reference

Implementation patterns for adding OpenCode-compatible web tools to a local Express.js proxy.

## server.mjs Snippet — Web Fetch

```javascript
async function fetchUrlContent(url, format) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  const fetchRes = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept-Language": "en-US,en;q=0.9",
    },
    signal: controller.signal
  });
  clearTimeout(timeout);

  if (!fetchRes.ok) throw new Error(`Fetch failed: ${fetchRes.statusText}`);
  const contentType = fetchRes.headers.get("content-type") || "";
  let output = await fetchRes.text();
  if (output.length > 5 * 1024 * 1024) throw new Error("Response too large (>5MB)");

  if (format === "markdown" && contentType.includes("html")) {
    const turndownService = new TurndownService();
    output = turndownService.turndown(output);
  }
  return { url, contentType, format, output };
}

app.post("/v1/web/fetch", async (req, res) => {
  const { url, format = "markdown" } = req.body;
  if (!url) return res.status(400).json({ error: "Missing url parameter" });
  try {
    const result = await fetchUrlContent(url, format);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
```

## server.mjs Snippet — Web Search

```javascript
app.post("/v1/web/search", async (req, res) => {
  const { query, action = "search", url } = req.body;

  try {
    // open_page action: fetch a specific URL
    if (action === "open_page" && url) {
      const result = await fetchUrlContent(url, "markdown");
      return res.json({ results: [{ title: url, url, snippet: result.output.substring(0, 1000) }] });
    }

    if (action !== "search" || !query) {
      return res.status(400).json({ error: "Invalid action or missing query" });
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    const searchUrl = `https://lite.duckduckgo.com/lite/`;
    const fetchRes = await fetch(searchUrl, {
      method: "POST",
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: `q=${encodeURIComponent(query)}`,
      signal: controller.signal
    });
    clearTimeout(timeout);
    if (!fetchRes.ok) throw new Error(`Search failed: ${fetchRes.statusText}`);

    const html = await fetchRes.text();
    const results = [];
    let currentResult = null;

    const parser = new htmlparser2.Parser({
      onopentag(name, attribs) {
        // DuckDuckGo Lite: <a rel="nofollow" href="URL" class="result-link">Title</a>
        if (name === "a" && attribs.class === "result-link") {
          currentResult = { url: attribs.href || "", title: "", snippet: "" };
        }
      },
      ontext(text) {
        if (!currentResult) return;
        const t = text.trim();
        if (!t) return;
        if (!currentResult.title) currentResult.title = t;
        else currentResult.snippet = (currentResult.snippet || "") + t + " ";
      },
      onclosetag(name) {
        if (name === "a" && currentResult && currentResult.title) {
          results.push({ ...currentResult });
          currentResult = null;
        }
      }
    });
    parser.write(html);
    parser.end();
    res.json({ results });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
```

## 🚨 Critical: Node.js fetch vs curl for DuckDuckGo

On GCP VMs (and some other environments), **Node.js v18's native `fetch()` gets a DIFFERENT response** from DuckDuckGo Lite than `curl` does. The Node.js response is shorter (~14KB vs ~24KB) and **lacks `result-link` class elements entirely**. This is a server-side detection issue (DuckDuckGo may be returning a simpler page based on the client's TLS fingerprint or headers).

### Symptoms
- Web search always returns `{"results":[]}`
- Testing with `curl` from the same VM works fine (returns results with `result-link` class)
- The HTML length from Node.js is ~14KB vs ~24KB from curl

### Fix: Use curl via child_process

Replace the `fetch()` call in the search handler with `child_process.execSync('curl ...')`:

```javascript
// Instead of fetch(), use curl via Node.js
import { execSync } from 'child_process';

// In the search handler:
const q = query.replace(/'/g, "'\\''");  // escape single quotes for shell
const curlCmd = `curl -sL 'https://lite.duckduckgo.com/lite/' \\
  -H 'User-Agent: Mozilla/5.0' \\
  -X POST -d 'q=${encodeURIComponent(query)}'`;

const html = execSync(curlCmd, { timeout: 15000, maxBuffer: 1024 * 1024 }).toString();

// Then parse the HTML with regex (not htmlparser2 — see below)
```

### Alternative: Regex-based Parsing (more reliable than htmlparser2)

When using curl output, htmlparser2 may still fail if class attributes use single quotes. Use regex instead:

```javascript
const linkRe = /<a[^>]+rel=['"]nofollow['"][^>]+href=['"]([^'"]+)['"][^>]*class=['"]result-link['"][^>]*>([^<]+)<\/a>/gi;
const snipRe = /<td class=['"]result-snippet['"]>([\s\S]*?)<\/td>/gi;
const links = [...html.matchAll(linkRe)];
const snips = [...html.matchAll(snipRe)];
const results = [];
for (let i = 0; i < links.length; i++) {
  const snippet = snips[i] ? snips[i][1].replace(/<[^>]*>/g, '').trim().substring(0, 300) : '';
  results.push({ title: links[i][2].trim(), url: links[i][1], snippet });
}
```

### Fallback: html.duckduckgo.com

If `lite.duckduckgo.com/lite/` fails, try `https://html.duckduckgo.com/html/` with HTML class `result__a` instead of `result-link`. This version may return more consistent results across different clients.

### Detection

To diagnose whether Node.js fetch is working:

```javascript
const html = await fetch('https://lite.duckduckgo.com/lite/', { method: 'POST', body: 'q=test' }).then(r => r.text());
console.log('Length:', html.length, 'Has results:', html.includes('result-link'));
// Length should be ~24KB+ — if it's ~14KB, fetch is broken
```

## Dependencies

```bash
npm install turndown htmlparser2
```

## Testing

```bash
# Web Fetch
curl -X POST http://localhost:4000/v1/web/fetch \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","format":"markdown"}'

# Web Search
curl -X POST http://localhost:4000/v1/web/search \
  -H "Content-Type: application/json" \
  -d '{"query":"test query"}'
```
