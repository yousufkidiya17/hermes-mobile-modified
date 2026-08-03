# Vision / Multimodal in the Embedded Engine (2026-08)

How images get from the app UI to the model through `hermes_agent.py` + `hermes_gateway.py`.
Verified end-to-end on PC (same code that runs on-device) with `mimo-v2.5-free`.

## Flow

```
App (ChatViewModel)
  ├─ gallery pick → image.attach_bytes RPC
  │     params: {session_id, content_base64: "data:<mime>;base64,...", filename, ext}
  │     → gateway handle_image_attach_bytes → sess["images"].append({mime, data})
  └─ prompt.submit {session_id, text}
        → handle_prompt_submit drains sess["images"] → data_uris list
        → process_chat(text, 20, data_uris)
              ├─ _build_user_content(text)  → text parts + @file: filesystem refs
              └─ merge data_uris as image_url parts
        → LLMClient.chat(messages)  (payload already OpenAI-multimodal shaped)
```

## Code shapes

### hermes_agent.py

```python
def process_chat(message, history_limit=20, images=None):
    ...
    user_content, image_refs = _build_user_content(message)   # @file: refs
    data_uis = images or []
    if data_uis:
        parts = [{"type": "text", "text": user_content}] if isinstance(user_content, str) else list(user_content)
        for du in data_uis:
            parts.append({"type": "image_url", "image_url": {"url": du}})
        user_content = parts
    messages.append({"role": "user", "content": user_content})
```

```python
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

def _build_user_content(message):
    refs = re.findall(r"@file:([^\s]+)", message)
    if not refs:
        return message, []
    parts = []
    text = re.sub(r"@file:\S+\s*", "", message).strip()
    if text:
        parts.append({"type": "text", "text": text})
    loaded = []
    for ref in refs:
        path = urllib.parse.unquote(ref)
        ext = os.path.splitext(path)[1].lower()
        if ext not in _IMAGE_EXTENSIONS:
            continue
        if os.path.exists(path):
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            mime = "image/png" if ext == ".png" else "image/gif" if ext == ".gif" \
                else "image/webp" if ext == ".webp" else "image/bmp" if ext == ".bmp" else "image/jpeg"
            parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
            loaded.append(path)
        else:
            parts.append({"type": "text", "text": f"[Image not found: {ref}]"})
    if not parts:
        return message, []
    if len(parts) == 1 and parts[0]["type"] == "text":
        return parts[0]["text"], loaded
    return parts, loaded
```

`base64` import must be added (it wasn't in the original import block — easy to miss).

### hermes_gateway.py

```python
# session dicts get an "images": [] key (in _ensure_session AND session.create)
def handle_image_attach_bytes(params):
    sid = params.get("session_id")
    content = params.get("content_base64", "")
    if content.startswith("data:"):
        header, _, b64 = content.partition(",")
        mime = header[5:].split(";")[0] or "image/png"
        sess["images"].append({"filename": params.get("filename","image"), "mime": mime, "data": b64})
        return {"attached": True, "session_id": sid}
    return {"attached": False, "error": "content_base64 must be a data URI"}
```

```python
# prompt.submit drains then clears:
sess = _sessions.get(sid, {})
staged = list(sess.get("images", []))
sess["images"] = []
data_uris = [f"data:{img['mime']};base64,{img['data']}" for img in staged]
result = await asyncio.to_thread(process_chat, text, 20, data_uris)
```

```python
_HANDLERS = {
    ...,
    "image.attach_bytes": handle_image_attach_bytes,   # sync handler (params only)
}
```

## Pitfalls (each cost a fix cycle)

1. **`handle_image_attach_bytes` must NOT take `ws`** — non-prompt handlers run via
   `asyncio.to_thread(handler, rpc_params)` (one arg). Giving it `(params, ws)` → TypeError at call time.
2. **`handle_session_interrupt` must stay `async`** — it's awaited directly in the prompt
   branch (`await handler(rpc_params, ws)`). Making it sync breaks that path.
3. **Don't forget `import base64`** in hermes_agent.py.
4. **Clear staged images after use** — otherwise they leak into the next prompt.
5. **`@file:` filesystem refs don't exist for gallery picks on-device** — the app uploads via
   `image.attach_bytes`; the `@file:` path is only for files the engine itself can read.
6. Model must be vision-capable — `mimo-v2.5-free` is (verified: red→"Red", blue→"Blue");
   if the model lacks vision the API errors or ignores image parts.

## Tiny test-image generator (no assets)

```python
import struct, zlib

def mkpng(color=(255, 0, 0)):
    def ch(tag, d):
        c = struct.pack(">I", len(d)) + tag + d
        return c + struct.pack(">I", zlib.crc32(tag + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)   # 2x2 RGB
    raw = b"".join(b"\x00" + bytes(color) * 2 for _ in range(2))
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", ihdr) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")
```

## Ad-hoc verification evidence (this session)

- `ast.parse` on both files → PASS
- `_build_user_content("color? @file:<red.png>")` → `[text, image_url(data:image/png;base64,...)]`
- `process_chat("What color? one word", images=[blue_data_uri])` → "Blue"
- Gateway WS: `session.create` → `image.attach_bytes` (attached:true) → `prompt.submit` → `message.complete` "Blue"
- Full suite (ktlint/lint/unit/instrumented) went green on the vision commit.
