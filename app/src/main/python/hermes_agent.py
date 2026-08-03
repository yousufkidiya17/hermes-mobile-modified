# Hermes Mobile Agent Engine - Python (Chaquopy embedded)
# Runs on-device via Chaquopy (bundled Python interpreter in APK).
# Kotlin calls these functions directly through Chaquopy's Python API.

import json
import os
import sys
import sqlite3
import threading
import base64
import urllib.request
import urllib.parse
import re
from pathlib import Path

# === Configuration ===
ZEN_API_URL = os.environ.get("ZEN_API_URL", "https://opencode.ai/zen/v1/chat/completions")
ZEN_API_KEY = os.environ.get("ZEN_API_KEY", "")
# OpenCode Zen expects the bare model name WITHOUT the "opencode/" prefix
# (the desktop LocalBridge strips it: .replace("opencode/", "")).
DEFAULT_MODEL = os.environ.get("ZEN_DEFAULT_MODEL", "mimo-v2.5-free")

MEMORY_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hermes_memory.db")

# === Memory (SQLite) — thread-safe ===
class Memory:
    def __init__(self, db_path=MEMORY_DB):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT)")
        self.conn.commit()

    def get(self, key, default=""):
        with self._lock:
            cur = self.conn.execute("SELECT value FROM memory WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set(self, key, value):
        with self._lock:
            self.conn.execute("REPLACE INTO memory (key, value) VALUES (?, ?)", (key, value))
            self.conn.commit()

    def add_message(self, role, content):
        with self._lock:
            self.conn.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
            self.conn.commit()

    def get_history(self, limit=50):
        with self._lock:
            cur = self.conn.execute("SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?", (limit,))
            return list(reversed(cur.fetchall()))

    def clear(self):
        with self._lock:
            self.conn.execute("DELETE FROM chat_history")
            self.conn.commit()

# === Skills Loader ===
class SkillsLoader:
    """Loads real Hermes skills (SKILL.md files) from the bundled skills/ tree.

    Hermes skills live in nested folders (e.g. skills/devops/docker/SKILL.md),
    so we walk the tree recursively. Each skill's name is its relative path
    (folder-based), matching how the desktop agent indexes them. Only the
    YAML frontmatter description is injected into the system prompt — full
    skill bodies would blow the context (54MB of markdown)."""

    def __init__(self, max_descriptions=400):
        self.skills = []
        self._index = {}
        skills_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
        if os.path.exists(skills_dir):
            for f in sorted(Path(skills_dir).rglob("SKILL.md")):
                try:
                    name = f.parent.name  # folder name, e.g. "docker"
                    rel = f.relative_to(skills_dir)
                    key = str(rel.parent).replace("\\", "/")  # e.g. "devops/docker"
                    text = f.read_text(encoding="utf-8", errors="replace")
                    desc = _skill_description(text)
                    self.skills.append({"name": name, "path": key, "content": text, "description": desc})
                    self._index[key] = self.skills[-1]
                except Exception:
                    continue
        # Sort by name for stable output
        self.skills.sort(key=lambda s: s["name"])

    def get_system_prompt(self, max_descriptions=400):
        base = "You are Hermes Agent, an intelligent AI assistant running on a phone.\n"
        if self.skills:
            lines = []
            for s in self.skills[:max_descriptions]:
                d = s["description"] or s["content"][:80].replace("\n", " ")
                lines.append(f"- {s['path']}: {d[:100]}")
            if len(self.skills) > max_descriptions:
                lines.append(f"- ... and {len(self.skills) - max_descriptions} more skills")
            return base + "\nAvailable Skills:\n" + "\n".join(lines)
        return base

    def get_skill(self, path):
        """Look up a skill by its relative path (e.g. 'devops/docker')."""
        return self._index.get(path)

    def list_skills(self):
        return [{"name": s["name"], "path": s["path"], "description": s["description"]} for s in self.skills]


def _skill_description(text):
    """Extract the `description:` value from a SKILL.md YAML frontmatter. Falls
    back to the first non-empty line if there's no frontmatter or no description."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            for line in fm.splitlines():
                stripped = line.strip()
                if stripped.startswith("description") or stripped.startswith("description:"):
                    val = stripped.split(":", 1)[1].strip().strip("\"'")
                    if val:
                        return val
    # fallback: first meaningful line
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("---"):
            return s[:120]
    return text[:120].replace("\n", " ")

# === LLM Client (direct to OpenCode Zen) ===
class LLMClient:
    def __init__(self, base_url=ZEN_API_URL, api_key=ZEN_API_KEY, model=DEFAULT_MODEL):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def chat(self, messages, stream=False):
        data = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }).encode()
        # Cloudflare (OpenCode Zen front) blocks Python-urllib's default UA
        # (error 1010). Use a browser-like User-Agent, same as the Node bridge.
        req = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"Error: {e}"

# === Tool Registry ===
class ToolRegistry:
    def __init__(self):
        self.tools = {}
        self._register_builtins()

    def _register_builtins(self):
        self.register("web_search", self.web_search, "Search the web via DuckDuckGo")
        self.register("web_fetch", self.web_fetch, "Fetch content from a URL")
        self.register("read_file", self.read_file, "Read a file from app storage")
        self.register("write_file", self.write_file, "Write content to a file")
        self.register("list_files", self.list_files, "List files in a directory")
        self.register("get_time", self.get_time, "Get current date and time")
        self.register("memory_get", self.memory_get, "Read a value from memory")
        self.register("memory_set", self.memory_set, "Store a value in memory")
        self.register("skill_search", self.skill_search, "Search installed skills by keyword")
        self.register("skill_get", self.skill_get, "Get the full content of a skill by path")
        self.register("calculator", self.calculator, "Evaluate a math expression safely")
        self.register("system_info", self.system_info, "Get device + engine information")
        self.register("run_command", self.run_command, "Run a shell command in the app sandbox")

    def register(self, name, handler, description=""):
        self.tools[name] = {"handler": handler, "description": description}

    def web_search(self, query, max_results=5):
        try:
            req = urllib.request.Request(
                f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}",
                # IMPORTANT: DDG returns a stripped page for Android UA (0 results).
                # Use plain Mozilla/5.0 or desktop UA to get full result links.
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                # Try multiple patterns to handle DuckDuckGo HTML changes
                results = re.findall(r'<a[^>]+class=["\']?result-link["\']?[^>]*>([^<]+)</a>', html)
                if not results:
                    results = re.findall(r'<a[^>]+rel=["\']nofollow["\'][^>]*>([^<]+)</a>', html)
                if not results:
                    results = re.findall(r'<a[^>]+href=["\']https?://(?!lite\.duckduckgo)[^"\'>]+["\'][^>]*>([^<]{10,})</a>', html)
                return json.dumps([{"title": r.strip()} for r in results[:max_results]])
        except Exception as e:
            return f"Search error: {e}"

    # Allowed URL schemes for web_fetch (prevent file:// SSRF)
    _ALLOWED_SCHEMES = ("http://", "https://")

    def web_fetch(self, url, max_chars=5000):
        try:
            if not any(url.lower().startswith(s) for s in self._ALLOWED_SCHEMES):
                return "Fetch error: only http:// and https:// URLs are allowed"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                return content[:max_chars]
        except Exception as e:
            return f"Fetch error: {e}"

    # Paths blocked from read/write to prevent path traversal
    _BLOCKED_PATHS = ("/etc/", "/proc/", "/sys/", "/dev/", "/system/")

    def _is_safe_path(self, path):
        resolved = os.path.realpath(path)
        return not any(resolved.startswith(b) for b in self._BLOCKED_PATHS)

    def read_file(self, path):
        try:
            if not self._is_safe_path(path):
                return "Read error: access to this path is blocked"
            with open(path, "r") as f:
                return f.read()
        except Exception as e:
            return f"Read error: {e}"

    def write_file(self, path, content):
        try:
            if not self._is_safe_path(path):
                return "Write error: access to this path is blocked"
            with open(path, "w") as f:
                f.write(content)
            return "File written successfully"
        except Exception as e:
            return f"Write error: {e}"

    def list_files(self, path="."):
        try:
            if not self._is_safe_path(path):
                return "List error: access to this path is blocked"
            files = os.listdir(path)
            return json.dumps(files[:50])
        except Exception as e:
            return f"List error: {e}"

    def get_time(self):
        from datetime import datetime
        return datetime.now().isoformat()

    def memory_get(self, key):
        return memory.get(key)

    def memory_set(self, key, value):
        memory.set(key, value)
        return "ok"

    def skill_search(self, query, limit=8):
        """Search installed skills by keyword (name, path, description)."""
        results = []
        q = query.lower()
        for s in skills.skills:
            haystack = f"{s['path']} {s['name']} {s.get('description') or ''}".lower()
            if q in haystack:
                results.append({"name": s["name"], "path": s["path"], "description": s.get("description") or ""})
                if len(results) >= limit:
                    break
        if not results and query.strip():
            for s in skills.skills:
                if any(tok in s["path"].lower() for tok in query.lower().split()):
                    results.append({"name": s["name"], "path": s["path"], "description": s.get("description") or ""})
                    if len(results) >= limit:
                        break
        return json.dumps(results or {"message": "No skills found for: " + query})

    def skill_get(self, path):
        """Fetch a skill's full SKILL.md content by its path (e.g. 'devops/docker')."""
        skill = skills.get_skill(path)
        if not skill:
            return json.dumps({"error": "Skill not found: " + path})
        content = skill["content"]
        if len(content) > 12000:
            content = content[:12000] + "\n...[truncated]"
        return json.dumps({"name": skill["name"], "path": skill["path"], "content": content})

    def calculator(self, expression):
        """Safely evaluate a math expression (numbers, + - * / ** % // parentheses)."""
        import ast as _ast
        allowed = {"Expression", "BinOp", "UnaryOp", "Add", "Sub", "Mult", "Div", "Mod", "FloorDiv", "Pow", "USub", "UAdd", "Constant"}
        try:
            tree = _ast.parse(expression, mode="eval")
            for node in _ast.walk(tree):
                if type(node).__name__ not in allowed:
                    return "Calculator error: unsupported expression"
            result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, {})
            return str(result)
        except Exception as e:
            return "Calculator error: " + str(e)

    def system_info(self):
        """Return device + engine information."""
        import platform
        return json.dumps({
            "platform": platform.system(),
            "python": platform.python_version(),
            "skills": len(skills.skills),
            "tools": list(tools.tools.keys()),
            "model": llm.model,
            "memory_keys": list(memory.db_dump().keys()) if hasattr(memory, "db_dump") else None,
        })

    def run_command(self, command, timeout=10):
        """Run a shell command inside the app sandbox (read-only safety: no rm/sudo)."""
        import subprocess
        cmd = command.strip()
        if not cmd:
            return "run_command: empty command"
        low = cmd.lower()
        for banned in ("rm -rf", "sudo", "mkfs", "dd if=", "shutdown", "reboot", "> /dev/sda"):
            if banned in low:
                return "run_command: command blocked (safety)"
        try:
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            out = (p.stdout or "")[:4000]
            err = (p.stderr or "")[:1000]
            return json.dumps({"exit": p.returncode, "stdout": out, "stderr": err})
        except subprocess.TimeoutExpired:
            return json.dumps({"exit": -1, "error": "timeout"})
        except Exception as e:
            return json.dumps({"exit": -1, "error": str(e)})

# === Agent Engine (single instance) ===
memory = Memory()
skills = SkillsLoader()
tools = ToolRegistry()
llm = LLMClient()


def process_chat(message, history_limit=20, images=None):
    """Main entry point: Kotlin calls this with a user message, gets a reply.
    Supports vision via two sources:
      - `@file:/path` refs in the message (filesystem images), and
      - `images` arg: list of base64 data-URIs staged by the gateway
        (from `image.attach_bytes`)."""
    history = memory.get_history()
    system_prompt = skills.get_system_prompt()

    messages = [{"role": "system", "content": system_prompt}]
    for role, content in history[-history_limit:]:
        messages.append({"role": role, "content": content})

    # Build user content — text + filesystem @file: refs first
    user_content, image_refs = _build_user_content(message)

    # Merge gateway-staged data-URI images (from image.attach_bytes)
    data_uis = images or []
    if data_uis:
        parts = [{"type": "text", "text": user_content}] if isinstance(user_content, str) else list(user_content)
        # Drop the placeholder text if it's the only stub when we have images
        for du in data_uis:
            parts.append({"type": "image_url", "image_url": {"url": du}})
        user_content = parts

    messages.append({"role": "user", "content": user_content})

    response = llm.chat(messages)
    memory.add_message("user", message)
    memory.add_message("assistant", response)

    return {"response": response, "model": llm.model, "images": list(image_refs)}


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _build_user_content(message):
    """Split a message into multimodal OpenAI content parts.
    Returns (content, image_refs):
      - content is a str (no images) or a list of content parts (with images).
      - image_refs is a list of image paths successfully loaded."""
    refs = re.findall(r"@file:([^\s]+)", message)
    if not refs:
        return message, []

    parts = []
    # Remove @file: refs from the visible text but keep the rest.
    text = re.sub(r"@file:\S+\s*", "", message).strip()
    if text:
        parts.append({"type": "text", "text": text})

    loaded = []
    for ref in refs:
        path = urllib.parse.unquote(ref)
        ext = os.path.splitext(path)[1].lower()
        if ext not in _IMAGE_EXTENSIONS:
            continue  # non-image refs are ignored for now
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                mime = "image/png" if ext == ".png" else \
                    "image/gif" if ext == ".gif" else \
                    "image/webp" if ext == ".webp" else \
                    "image/bmp" if ext == ".bmp" else "image/jpeg"
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
                loaded.append(path)
            except Exception:
                pass
        else:
            parts.append({"type": "text", "text": f"[Image not found: {ref}]"})

    if not parts:
        return message, []
    if len(parts) == 1 and parts[0]["type"] == "text":
        return parts[0]["text"], loaded
    return parts, loaded


def run_tool(name, args=None, kwargs=None):
    """Kotlin calls this to execute a tool by name."""
    args = args or []
    kwargs = kwargs or {}
    if name in tools.tools:
        result = tools.tools[name]["handler"](*args, **kwargs)
        return {"ok": True, "result": result}
    return {"ok": False, "error": f"Tool '{name}' not found"}


def list_tools():
    return {"tools": list(tools.tools.keys())}


def list_skills():
    return {"skills": [s["name"] for s in skills.skills]}


def get_status():
    return {
        "status": "ok",
        "engine": "Hermes Mobile Agent (Chaquopy)",
        "python": sys.version.split()[0],
        "tools": list(tools.tools.keys()),
        "skills": len(skills.skills),
        "model": llm.model,
    }


def get_status_json():
    """JSON-string variant of get_status — Chaquopy PyObject auto-conversion
    of nested lists is unreliable on some devices, so Kotlin parses this
    instead of reading PyObject fields directly."""
    return json.dumps(get_status())


def set_model(model_name):
    llm.model = model_name
    return {"ok": True, "model": llm.model}


def clear_memory():
    memory.clear()
    return {"ok": True}


# === HTTP Server (optional — for external clients) ===
import http.server


class AgentHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._json(get_status())
        elif self.path == "/tools":
            self._json(list_tools())
        elif self.path == "/skills":
            self._json(list_skills())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = self._read_body()
        if self.path == "/chat":
            self._json(process_chat(body.get("message", "")))
        elif self.path == "/tool":
            self._json(run_tool(body.get("tool"), body.get("args"), body.get("kwargs")))
        elif self.path == "/memory":
            memory.set(body.get("key"), body.get("value"))
            self._json({"status": "ok"})
        else:
            self._json({"error": "not found"}, 404)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass


def start_http_server(port=5000):
    """Start HTTP server in a background thread (for external clients)."""
    server = http.server.HTTPServer(("127.0.0.1", port), AgentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return {"ok": True, "port": port}


if __name__ == "__main__":
    print(f"Hermes Mobile Agent Engine")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Tools: {list(tools.tools.keys())}")
    print(f"Skills: {len(skills.skills)}")
    print("Starting HTTP server on :5000")
    start_http_server()
    # Keep alive
    import time
    while True:
        time.sleep(60)
