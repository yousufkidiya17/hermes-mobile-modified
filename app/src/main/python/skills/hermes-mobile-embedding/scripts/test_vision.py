#!/usr/bin/env python3
"""Ad-hoc verification: vision support in hermes_agent.py + hermes_gateway.py.

Builds a tiny in-memory PNG (no image asset needed), confirms @file: refs turn into
OpenAI multimodal data-URI content, checks gateway wiring, and does a live LLM
regression + a vision LLM call. Runs the SAME code that ships on-device (Chaquopy),
so success here is strong evidence the phone build will handle images.

Usage:
    python test_vision.py [--gateway-path <hermes_gateway.py>] [--skip-live]

--skip-live skips the real model calls (network) and only checks syntax/wiring.
"""
import argparse
import ast
import os
import struct
import sys
import zlib

PY = os.path.dirname(os.path.abspath(__file__))
# Allow running from anywhere: this script lives in skills/scripts/.
HERMES_PY = os.path.join(PY, "..", "app", "src", "main", "python")
HERMES_PY = os.path.abspath(os.environ.get("HERMES_PYTHON_DIR", HERMES_PY))


def run(gateway=True, live=True):
    report = []
    report.append("=== AD-HOC VERIFICATION: Vision (hermes_agent/hermes_gateway) ===")
    ok = True

    files = ["hermes_gateway.py"] if gateway else []
    files.append("hermes_agent.py")
    for f in files:
        p = os.path.join(HERMES_PY, f)
        if not os.path.exists(p):
            report.append(f"[syntax] SKIP {f} (not found) — set HERMES_PYTHON_DIR")
            continue
        try:
            ast.parse(open(p, encoding="utf-8").read())
            report.append(f"[syntax] PASS {f}")
        except SyntaxError as e:
            report.append(f"[syntax] FAIL {f}: {e}")
            ok = False

    if gateway:
        gw = open(os.path.join(HERMES_PY, "hermes_gateway.py"), encoding="utf-8").read()
        for label, needle in [
            ("image.attach_bytes registered", "image.attach_bytes"),
            ("prompt.submit passes data_uris", "process_chat, text, 20, data_uris"),
            ("sessions store images", '"images"'),
        ]:
            found = needle in gw
            report.append(f"[gateway] {'PASS' if found else 'FAIL'} {label}")
            ok = ok and found

    sys.path.insert(0, HERMES_PY)
    for m in list(sys.modules):
        if m.startswith("hermes_agent"):
            del sys.modules[m]
    import hermes_agent as ha

    def mkpng(color=(255, 0, 0)):
        def ch(tag, d):
            c = struct.pack(">I", len(d)) + tag + d
            return c + struct.pack(">I", zlib.crc32(tag + d) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
        raw = b"".join(b"\x00" + bytes(color) * 2 for _ in range(2))
        return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", ihdr) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")

    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "hermes-verify-vision.png")
    open(tmp, "wb").write(mkpng((255, 255, 0)))
    content, refs = ha._build_user_content(f"what color? @file:{tmp}")
    multi = isinstance(content, list) and any(p.get("type") == "image_url" for p in content)
    report.append(f"[engine] {'PASS' if multi else 'FAIL'} @file -> multimodal content ({len(refs)} img)")
    ok = ok and multi
    try:
        os.remove(tmp)
    except Exception:
        pass

    if live:
        import base64
        blue_uri = "data:image/png;base64," + base64.b64encode(mkpng((0, 0, 255))).decode()
        r = ha.process_chat("What color is this? Reply with just the color name.", images=[blue_uri])
        report.append(f"[engine] {'PASS' if r.get('response') else 'FAIL'} vision LLM -> {r.get('response','')[:20]}")
        ok = ok and bool(r.get("response"))
        r2 = ha.process_chat("Reply with exactly: OK")
        report.append(f"[engine] {'PASS' if r2.get('response')=='OK' else 'FAIL'} text regression -> {r2.get('response','')}")
        ok = ok and r2.get("response") == "OK"
    else:
        report.append("[engine] SKIP live LLM (--skip-live)")

    report.append(f"\nVERDICT: {'PASS' if ok else 'FAIL'} (ad-hoc; full suite = GitHub CI)")
    print("\n".join(report))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--no-gateway", action="store_true")
    args = ap.parse_args()
    sys.exit(run(gateway=not args.no_gateway, live=not args.skip_live))