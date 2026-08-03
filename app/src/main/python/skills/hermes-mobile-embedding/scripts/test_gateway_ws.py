#!/usr/bin/env python3
"""Smoke-test the Hermes Mobile on-device gateway (hermes_gateway.py, port 9119).

Verifies the full chain the app uses:
  REST probes (status/health/root token) + WebSocket JSON-RPC + live LLM reply.

Prereqs:
  pip install websockets
  # terminal 1: python app/src/main/python/hermes_gateway.py
  # terminal 2: python scripts/test_gateway_ws.py [--no-llm]
Pass --no-llm to skip the live model call (just protocol + session flow).
"""
import argparse
import asyncio
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:9119"
WS = "ws://127.0.0.1:9119/api/ws?token=hermes-mobile-token"


def check_rest():
    print("=== REST probes ===")
    for path, expect in [
        ("/api/status", "auth_required"),
        ("/api/health", "status"),
        ("/", "__HERMES_SESSION_TOKEN__"),
    ]:
        try:
            body = urllib.request.urlopen(BASE + path, timeout=5).read().decode()
            ok = expect in body
            print(f"  {'✅' if ok else '❌'} GET {path} -> found '{expect}'")
            if not ok:
                sys.exit(1)
        except Exception as e:
            print(f"  ❌ GET {path} -> {e}")
            sys.exit(1)


async def check_ws(do_llm: bool):
    import websockets

    print("=== WebSocket JSON-RPC ===")
    async with websockets.connect(WS) as ws:
        ready = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        evt = ready.get("params", {}).get("type")
        assert evt == "gateway.ready", f"expected gateway.ready, got {evt}"
        print("  ✅ gateway.ready event")

        async def rpc(req_id, method, params=None):
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {},
            }))
            return json.loads(await asyncio.wait_for(ws.recv(), timeout=10))

        resp = await rpc("1", "session.create")
        sid = resp.get("result", {}).get("session_id")
        assert sid, f"session.create failed: {resp}"
        print(f"  ✅ session.create -> {sid}")

        resp = await rpc("2", "session.status", {"session_id": sid})
        assert resp.get("result", {}).get("status") == "active"
        print("  ✅ session.status -> active")

        resp = await rpc("3", "commands.catalog")
        n = len(resp.get("result", {}).get("commands", []))
        print(f"  ✅ commands.catalog -> {n} commands")

        if not do_llm:
            print("  ⏭  --no-llm: skipping prompt.submit")
            return

        print("  📤 prompt.submit 'Hello! Reply with just OK'")
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": "4", "method": "prompt.submit",
            "params": {"session_id": sid, "text": "Hello! Reply with just OK"},
        }))
        events = []
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=90)
            msg = json.loads(raw)
            if msg.get("method") == "event":
                evt_type = msg["params"]["type"]
                events.append(evt_type)
                if evt_type == "message.delta":
                    print(f"      delta: {msg['params']['payload'].get('text','')[:60]!r}")
                elif evt_type == "message.complete":
                    print(f"  ✅ complete: {msg['params']['payload'].get('text','')[:80]!r}")
                elif evt_type == "message.done":
                    break
            elif "result" in msg:
                break
        expected = ["message.start", "message.delta", "message.complete", "message.done"]
        assert all(e in events for e in expected), f"missing events: {events}"
        print(f"  ✅ full stream: {events}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="skip live model call")
    args = ap.parse_args()
    check_rest()
    asyncio.run(check_ws(not args.no_llm))
    print("\n🎉 Gateway smoke test PASSED")


if __name__ == "__main__":
    main()
