# Hermes Mobile Agent Engine - Python (Chaquopy embedded)
# Runs on-device via Chaquopy (bundled Python interpreter in APK).
# Kotlin calls these functions directly through Chaquopy's Python API.

import json
import os
import sys
import sqlite3
import threading
import urllib.request
import urllib.parse
import re
from pathlib import Path

# === Configuration ===
ZEN_API_URL = os.environ.get("ZEN_API_URL", "https://opencode.ai/zen/v1/chat/completions")
ZEN_API_KEY = os.environ.get("ZEN_API_KEY", "")
DEFAULT_MODEL = os.environ.get("ZEN_DEFAULT_MODEL", "opencode/mimo-v2.5-free")

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
    def __init__(self):
        self.skills = []
        skills_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
        if os.path.exists(skills_dir):
            for f in Path(skills_dir).glob("*.md"):
                self.skills.append({"name": f.stem, "content": f.read_text()})

    def get_system_prompt(self):
        base = "You are Hermes Agent, an intelligent AI assistant running on a phone."
        if self.skills:
            skills_text = "\n\nAvailable Skills:\n" + "\n".join(f"- {s['name']}: {s['content'][:100]}" for s in self.skills)
            return base + skills_text
        return base

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
        req = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Content-Type": "application/json",
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

    def register(self, name, handler, description=""):
        self.tools[name] = {"handler": handler, "description": description}

    def web_search(self, query, max_results=5):
        try:
            req = urllib.request.Request(
                f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}",
                headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36"},
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

# === Agent Engine (single instance) ===
memory = Memory()
skills = SkillsLoader()
tools = ToolRegistry()
llm = LLMClient()


def process_chat(message, history_limit=20):
    """Main entry point: Kotlin calls this with a user message, gets a reply."""
    history = memory.get_history()
    system_prompt = skills.get_system_prompt()

    messages = [{"role": "system", "content": system_prompt}]
    for role, content in history[-history_limit:]:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    response = llm.chat(messages)
    memory.add_message("user", message)
    memory.add_message("assistant", response)

    return {"response": response, "model": llm.model}


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
