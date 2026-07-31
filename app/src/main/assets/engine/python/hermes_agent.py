# Hermes Mobile Agent Engine - Python
# Runs on-device via libtermux, connects to LocalBridge for LLM inference

import json
import sys
import os
import http.server
import urllib.request
import urllib.error
import threading
import sqlite3
from pathlib import Path

# === Configuration ===
LOCALBRIDGE_URL = "http://127.0.0.1:4000/v1/chat/completions"
ENGINE_PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 5000
SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "skills")
MEMORY_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hermes_memory.db")

# === Memory (SQLite) ===
class Memory:
    def __init__(self, db_path=MEMORY_DB):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT)")
        self.conn.commit()
    
    def get(self, key, default=""):
        cur = self.conn.execute("SELECT value FROM memory WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default
    
    def set(self, key, value):
        self.conn.execute("REPLACE INTO memory (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()
    
    def add_message(self, role, content):
        self.conn.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
        self.conn.commit()
    
    def get_history(self, limit=50):
        cur = self.conn.execute("SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?", (limit,))
        return list(reversed(cur.fetchall()))

# === Skills Loader ===
class SkillsLoader:
    def __init__(self, skills_dir=SKILLS_DIR):
        self.skills = []
        if os.path.exists(skills_dir):
            for f in Path(skills_dir).glob("*.md"):
                self.skills.append({"name": f.stem, "content": f.read_text()})
    
    def get_system_prompt(self):
        base = "You are Hermes Agent, an intelligent AI assistant. You have access to tools and skills."
        if self.skills:
            skills_text = "\n\nAvailable Skills:\n" + "\n".join(f"- {s['name']}: {s['content'][:100]}" for s in self.skills)
            return base + skills_text
        return base

# === LocalBridge Client ===
class LLMClient:
    def __init__(self, base_url=LOCALBRIDGE_URL):
        self.base_url = base_url
    
    def chat(self, messages, stream=False):
        data = json.dumps({
            "model": "opencode/mimo-v2.5-free",
            "messages": messages,
            "stream": stream
        }).encode()
        req = urllib.request.Request(
            self.base_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"Error: {e}"

# === Tool Handlers ===
class ToolRegistry:
    def __init__(self):
        self.tools = {}
        self._register_builtins()
    
    def _register_builtins(self):
        self.register("web_search", self.web_search, "Search the web for information")
        self.register("web_fetch", self.web_fetch, "Fetch content from a URL")
        self.register("read_file", self.read_file, "Read a file from storage")
        self.register("write_file", self.write_file, "Write content to a file")
        self.register("list_files", self.list_files, "List files in a directory")
        self.register("run_command", self.run_command, "Run a shell command")
        self.register("get_time", self.get_time, "Get current date and time")
    
    def register(self, name, handler, description=""):
        self.tools[name] = {"handler": handler, "description": description}
    
    def web_search(self, query):
        try:
            req = urllib.request.Request(
                f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode()
                import re
                results = re.findall(r'<a[^>]+class=.result-link.[^>]*>([^<]+)</a>', html)
                return json.dumps([{"title": r.strip()} for r in results[:5]])
        except Exception as e:
            return f"Search error: {e}"
    
    def web_fetch(self, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                return content[:5000]
        except Exception as e:
            return f"Fetch error: {e}"
    
    def read_file(self, path):
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception as e:
            return f"Read error: {e}"
    
    def write_file(self, path, content):
        try:
            with open(path, "w") as f:
                f.write(content)
            return "File written successfully"
        except Exception as e:
            return f"Write error: {e}"
    
    def list_files(self, path="."):
        try:
            files = os.listdir(path)
            return json.dumps(files[:50])
        except Exception as e:
            return f"List error: {e}"
    
    def run_command(self, command):
        try:
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            return result.stdout[:5000] or result.stderr[:5000]
        except Exception as e:
            return f"Command error: {e}"
    
    def get_time(self):
        from datetime import datetime
        return datetime.now().isoformat()

# === Agent HTTP Server ===
class AgentHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._json({"status": "ok", "engine": "Hermes Mobile Agent"})
        elif self.path == "/tools":
            self._json({"tools": list(server.tools.tools.keys())})
        elif self.path.startswith("/memory/"):
            key = self.path[8:]
            self._json({"value": server.memory.get(key)})
        else:
            self._json({"error": "not found"}, 404)
    
    def do_POST(self):
        body = self._read_body()
        if self.path == "/chat":
            response = server.process_chat(body)
            self._json(response)
        elif self.path == "/memory":
            server.memory.set(body.get("key"), body.get("value"))
            self._json({"status": "ok"})
        elif self.path == "/tool":
            tool_name = body.get("tool")
            args = body.get("args", [])
            kwargs = body.get("kwargs", {})
            if tool_name in server.tools.tools:
                result = server.tools.tools[tool_name]["handler"](*args, **kwargs)
                self._json({"result": result})
            else:
                self._json({"error": f"Tool '{tool_name}' not found"}, 404)
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
        pass  # Suppress logs

class AgentServer:
    def __init__(self):
        self.memory = Memory()
        self.skills = SkillsLoader()
        self.tools = ToolRegistry()
        self.llm = LLMClient()
    
    def process_chat(self, body):
        message = body.get("message", "")
        history = self.memory.get_history()
        system_prompt = self.skills.get_system_prompt()
        
        messages = [{"role": "system", "content": system_prompt}]
        for role, content in history[-20:]:
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        
        response = self.llm.chat(messages)
        self.memory.add_message("user", message)
        self.memory.add_message("assistant", response)
        
        return {"response": response, "model": "mimo-v2.5-free"}

# === Main ===
if __name__ == "__main__":
    import urllib.parse
    
    server = AgentServer()
    http_server = http.server.HTTPServer(("127.0.0.1", ENGINE_PORT), AgentHandler)
    print(f"Hermes Mobile Agent Engine running on port {ENGINE_PORT}")
    print(f"LocalBridge: {LOCALBRIDGE_URL}")
    print(f"Skills loaded: {len(server.skills.skills)}")
    print(f"Tools available: {list(server.tools.tools.keys())}")
    
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        http_server.shutdown()
