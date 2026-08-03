# Hermes Mobile Gateway - WebSocket JSON-RPC server (port 9119)
# Speaks the Hermes TUI gateway protocol so the Hermes Mobile app can connect
# directly to the on-device engine. Pure Python (stdlib + websockets lib).
#
# Flow:
#   App --WS--> hermes_gateway (9119) --> hermes_agent (LLM via OpenCode Zen)
#
# Protocol (mirrors tui_gateway/server.py):
#   Request:  {"jsonrpc":"2.0","id":"<str>","method":"<name>","params":{...}}
#   Response: {"jsonrpc":"2.0","id":"<str>","result":{...}}
#             {"jsonrpc":"2.0","id":"<str>","error":{"code":N,"message":"..."}}
#   Event:    {"jsonrpc":"2.0","method":"event","params":{"type":"<evt>","session_id":"...","payload":{...}}}

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

# Ensure hermes_agent module (same dir) is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log = logging.getLogger("hermes_gateway")

GATEWAY_PORT = int(os.environ.get("HERMES_GATEWAY_PORT", "9119"))
TOKEN = os.environ.get("HERMES_GATEWAY_TOKEN", "")

# ---------------------------------------------------------------------------
# Session store (in-memory; SQLite persistence lives in hermes_agent.Memory)
# ---------------------------------------------------------------------------
_sessions = {}  # session_id -> {"title": str, "created": float, "messages": int}


def _new_session_id():
    return uuid.uuid4().hex[:12]


def _session_dict(sid):
    s = _sessions.get(sid, {})
    return {
        "session_id": sid,
        "title": s.get("title", "New Chat"),
        "created_at": s.get("created", 0),
        "message_count": s.get("messages", 0),
    }


def _ensure_session(sid):
    if sid and sid not in _sessions:
        _sessions[sid] = {"title": "New Chat", "created": time.time(), "messages": 0, "images": []}
    return sid or _new_session_id()


# ---------------------------------------------------------------------------
# JSON-RPC handlers (methods the app calls; names from WsMethods.kt)
# ---------------------------------------------------------------------------
def handle_session_list(params):
    return {"sessions": [_session_dict(s) for s in _sessions]}


def handle_session_active_list(params):
    # Return the most recently touched session (or none)
    if _sessions:
        sid = max(_sessions, key=lambda k: _sessions[k].get("created", 0))
        return {"session": _session_dict(sid)}
    return {"session": None}


def handle_session_create(params):
    sid = _new_session_id()
    _sessions[sid] = {"title": "New Chat", "created": time.time(), "messages": 0, "images": []}
    return _session_dict(sid)


def handle_session_resume(params):
    sid = params.get("session_id") or params.get("id")
    sid = _ensure_session(sid)
    return _session_dict(sid)


def handle_session_status(params):
    sid = params.get("session_id")
    if sid and sid in _sessions:
        return {"status": "active", "session": _session_dict(sid)}
    return {"status": "idle", "session": None}


def handle_session_history(params):
    sid = params.get("session_id")
    history = []
    if sid:
        try:
            from hermes_agent import memory
            history = [
                {"role": role, "content": content}
                for role, content in memory.get_history(50)
            ]
        except Exception as e:
            log.warning("history via memory failed: %s", e)
    return {"messages": history, "session_id": sid}


def handle_commands_catalog(params):
    return {
        "commands": [
            {"name": "help", "description": "Show help"},
            {"name": "new", "description": "Start a new chat"},
            {"name": "clear", "description": "Clear conversation"},
            {"name": "model", "description": "Show / change model"},
            {"name": "tools", "description": "List available tools"},
        ]
    }


# ---------------------------------------------------------------------------
# Main prompt handler — streams events, returns final text
# ---------------------------------------------------------------------------
async def handle_prompt_submit(params, ws):
    sid = params.get("session_id")
    text = params.get("text", "")
    sid = _ensure_session(sid)
    _sessions[sid]["messages"] = _sessions[sid].get("messages", 0) + 1

    # message.start
    await _emit(ws, "message.start", sid, {"session_id": sid})

    try:
        from hermes_agent import process_chat
        # Pass any gateway-staged images (image.attach_bytes) as data-URIs,
        # then clear them so they don't leak into the next message.
        sess = _sessions.get(sid, {})
        staged = list(sess.get("images", []))
        sess["images"] = []
        data_uris = [f"data:{img['mime']};base64,{img['data']}" for img in staged]
        result = await asyncio.to_thread(process_chat, text, 20, data_uris)
        reply = result.get("response", "") if isinstance(result, dict) else str(result)
        model = result.get("model", "") if isinstance(result, dict) else ""
    except Exception as e:
        log.exception("prompt.submit failed")
        reply = f"Engine error: {e}"
        model = ""

    # Stream the reply in chunks (message.delta) then complete
    chunk = 120
    for i in range(0, len(reply), chunk):
        await _emit(
            ws,
            "message.delta",
            sid,
            {"session_id": sid, "text": reply[i : i + chunk]},
        )
    await _emit(
        ws,
        "message.complete",
        sid,
        {"session_id": sid, "text": reply, "model": model},
    )
    await _emit(ws, "message.done", sid, {"session_id": sid})

    # RPC result for prompt.submit itself
    return {"status": "ok", "session_id": sid}


async def handle_session_interrupt(params, ws):
    # No long-running agent loop in this lightweight engine — nothing to stop.
    return {"status": "ok"}


def handle_image_attach_bytes(params):
    """Stage an image (base64 data URI) into the session so the next prompt.submit
    sends it as multimodal content. Mirrors the app's `image.attach_bytes` RPC."""
    sid = params.get("session_id")
    content = params.get("content_base64", "")  # "data:image/png;base64,...."
    filename = params.get("filename", "image")
    if not sid:
        return {"error": "session_id required", "attached": False}
    sess = _sessions.setdefault(sid, {"title": "New Chat", "created": time.time(), "messages": 0, "images": []})
    sess.setdefault("images", [])
    if content.startswith("data:"):
        header, _, b64 = content.partition(",")
        mime = header[5:].split(";")[0] or "image/png"
        sess["images"].append(
            {"filename": filename, "mime": mime, "data": b64}
        )
        log.info("image attached to session %s (%s,%dB)", sid, mime, len(b64))
        return {"attached": True, "session_id": sid}
    return {"attached": False, "error": "content_base64 must be a data URI"}


_HANDLERS = {
    "session.list": handle_session_list,
    "session.active_list": handle_session_active_list,
    "session.create": handle_session_create,
    "session.resume": handle_session_resume,
    "session.status": handle_session_status,
    "session.history": handle_session_history,
    "commands.catalog": handle_commands_catalog,
    "prompt.submit": handle_prompt_submit,
    "session.interrupt": handle_session_interrupt,
    "image.attach_bytes": handle_image_attach_bytes,
}


# ---------------------------------------------------------------------------
# WebSocket plumbing (websockets library)
# ---------------------------------------------------------------------------
async def _emit(ws, evt_type, sid, payload):
    msg = {
        "jsonrpc": "2.0",
        "method": "event",
        "params": {"type": evt_type, "session_id": sid, "payload": payload},
    }
    try:
        await ws.send(json.dumps(msg))
    except Exception as e:
        log.warning("emit %s failed: %s", evt_type, e)


async def _send_result(ws, req_id, result):
    await ws.send(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}))


async def _send_error(ws, req_id, code, message):
    await ws.send(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": code, "message": message},
            }
        )
    )


async def _gateway_ready(ws):
    await ws.send(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "gateway.ready",
                    "session_id": None,
                    "payload": {"version": "0.1.0-mobile"},
                },
            }
        )
    )


async def handle_connection(ws):
    # Token check: /api/ws?token=... — if gateway requires a token, verify it
    path = getattr(ws, "path", "") or ""
    query = path.split("?", 1)[1] if "?" in path else ""
    params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
    token = params.get("token", "")
    if TOKEN and token != TOKEN:
        await _send_error(ws, None, 4010, "Invalid token")
        await ws.close(code=4401)
        return

    log.info("client connected")
    await _gateway_ready(ws)

    try:
        async for raw in ws:
            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                continue

            req_id = req.get("id")
            method = req.get("method")
            rpc_params = req.get("params") or {}

            if method == "prompt.submit" or method == "session.interrupt":
                handler = _HANDLERS.get(method)
                result = await handler(rpc_params, ws)
                if req_id is not None:
                    await _send_result(ws, req_id, result)
                continue

            handler = _HANDLERS.get(method)
            if handler is None:
                if req_id is not None:
                    await _send_error(ws, req_id, -32601, f"Method not found: {method}")
                continue

            try:
                result = await asyncio.to_thread(handler, rpc_params)
            except Exception as e:
                log.exception("handler %s failed", method)
                result = {"error": str(e)}
            if req_id is not None:
                await _send_result(ws, req_id, result)
    except Exception as e:
        log.warning("connection error: %s", e)
    finally:
        log.info("client disconnected")


def start_gateway_sync():
    """Entry point called from Kotlin (Chaquopy) — runs the asyncio loop."""
    import websockets
    from websockets.datastructures import Headers
    from websockets.http11 import Response

    # REST endpoints the app probes before connecting the WebSocket:
    #   GET /api/status   -> auth mode discovery (AuthLoginViewModel.probe)
    #   GET /api/health   -> dashboard health check
    # These return plain HTTP JSON so the app's OkHttp probe succeeds.
    # (websockets >= 14 passes (connection, request); request.path has the path.)
    def process_request(connection, request):
        path = request.path
        if path == "/api/status":
            payload = {
                "status": "ok",
                "auth_required": False,
                "auth_providers": [],
                "version": "0.1.0-mobile",
                "service": "Hermes Mobile Gateway",
            }
            body = json.dumps(payload).encode()
            return Response(200, "OK", Headers({"Content-Type": "application/json"}), body)
        if path == "/api/health":
            body = json.dumps({"status": "ok", "service": "Hermes Mobile"}).encode()
            return Response(200, "OK", Headers({"Content-Type": "application/json"}), body)
        if path == "/api/skills":
            # App's SkillsScreen calls GET api/skills -> List<Skill>
            try:
                from hermes_agent import skills as _skills_loader, list_skills
                payload = []
                for s in _skills_loader.skills:
                    payload.append({
                        "name": s["name"],
                        "description": s.get("description") or "",
                        "category": s["path"].split("/")[0] if "/" in s["path"] else "general",
                        "enabled": True,
                        "source": "built-in",
                    })
                body = json.dumps(payload).encode()
                return Response(200, "OK", Headers({"Content-Type": "application/json"}), body)
            except Exception as e:
                log.exception("api/skills failed")
                body = json.dumps([]).encode()
                return Response(200, "OK", Headers({"Content-Type": "application/json"}), body)
        if path == "/api/tools":
            try:
                from hermes_agent import list_tools
                payload = [{"name": t, "description": "", "enabled": True} for t in list_tools()["tools"]]
                body = json.dumps(payload).encode()
                return Response(200, "OK", Headers({"Content-Type": "application/json"}), body)
            except Exception:
                body = json.dumps([]).encode()
                return Response(200, "OK", Headers({"Content-Type": "application/json"}), body)
        if path == "/" or path == "/api":
            # The app (AuthLoginViewModel) fetches the root page and extracts the
            # session token from __HERMES_SESSION_TOKEN__ (loopback mode). Embed it
            # so the login auto-populates and skips the manual token prompt.
            body = (
                "<!DOCTYPE html><html><head><title>Hermes Mobile Gateway</title></head>"
                "<body>"
                "<script>window.__HERMES_SESSION_TOKEN__ = \"hermes-mobile-token\";</script>"
                "<h1>Hermes Mobile Gateway</h1>"
                "<p>WebSocket: /api/ws</p>"
                "</body></html>"
            ).encode()
            return Response(200, "OK", Headers({"Content-Type": "text/html"}), body)
        # Anything else -> let the WebSocket layer handle it (404 for non-WS).
        return None

    async def main():
        async with websockets.serve(
            handle_connection,
            "127.0.0.1",
            GATEWAY_PORT,
            process_request=process_request,
        ):
            log.info("Hermes Mobile Gateway listening on ws://127.0.0.1:%s/api/ws", GATEWAY_PORT)
            await asyncio.Future()  # run forever

    asyncio.run(main())


def start_gateway_background():
    """Start the gateway in a background thread (so the Python module import
    returns immediately and Kotlin keeps control of the main thread)."""
    import threading

    t = threading.Thread(target=start_gateway_sync, daemon=True)
    t.start()
    return {"ok": True, "port": GATEWAY_PORT}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Hermes Mobile Gateway starting on ws://127.0.0.1:{GATEWAY_PORT}/api/ws")
    start_gateway_sync()
