---
name: personality-rag
description: "Build AI personality clones using RAG from public content."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [RAG, personality, clone, AI, embeddings, vector-db, mimicry]
    related_skills: [chroma, youtube-content, dspy]
---

# Personality RAG — AI Personality Cloning

Build an AI that talks EXACTLY like a specific person (comedian, influencer, celebrity, character) by collecting their public speech, chunking it, embedding it, and using it as a live style reference. The goal is **mannerism mimicry, not fact retrieval** — the RAG feeds the model *how* they say things, not just *what* they know.

## When to Use
- User wants an AI that mimics a real person's speaking style, vocabulary, tone
- Building a comedy / entertainment / roast AI character
- "Samay Raina AI", "X ka AI clone" type requests
- User provides YouTube links or content sources of a specific person

## Workflow

### Step 1: Data Collection — Source Priority

| Source | Quality | Why |
|--------|---------|-----|
| 🥇 **Comedy specials / solo vlogs** | ✅ Perfect | 100% their voice, no speaker overlap |
| 🥈 **Social media posts** (Twitter, Instagram) | ✅ Great | Their writing, raw personality |
| ⚠️ **Interviews (their answers only)** | ⚠️ OK | Need to extract only their parts |
| ❌ **Podcasts / group streams** | ❌ Avoid | Multiple speakers — needs diarization |

Use `youtube-content` skill to fetch transcripts:
```bash
uv run python3 <youtube-skill>/scripts/fetch_transcript.py "URL" --text-only > data/video_name.txt
```
Save each transcript to a separate `.txt` file in a dedicated `data/` folder.

### Step 2: Chunking for Style (not for facts)

Smaller chunks = better style signal:

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,       # short — captures a single bit/joke
    chunk_overlap=50,     # small overlap for continuity
    separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""]
)
chunks = splitter.split_text(full_transcript)
```

Each chunk should capture one **style unit** — a punchline, a roast, a reaction.

### Step 3: Embed + Store (Chroma)

```bash
pip install chromadb sentence-transformers
```

```python
import chromadb

client = chromadb.PersistentClient(path="./persona_db")
# Name collection after the person, not the session
collection = client.create_collection(name="persona_name")

collection.add(
    documents=chunks,
    metadatas=[
        {"source": "special_2026", "type": "standup", "mood": "roast"},
        {"source": "interview", "type": "chat", "mood": "casual"},
    ],
    ids=[f"chunk_{i:04d}" for i in range(len(chunks))]
)
```

### Step 4: Personality System Prompt

The system prompt is the **second layer** of the clone. The RAG provides raw style examples; the prompt locks the persona:

```
You are [Person Name]. Talk exactly like them.
- Use their vocabulary, catchphrases, and filler words.
- Match their language mix (e.g. Hinglish, street Hindi).
- Copy their joke structure, timing, pause markers.
- Never break character.
- If they use gaalis/slangs, you can too in the same spirit.
```

### Step 5: Query → RAG → Generate

```python
# 1. Retrieve relevant style chunks
results = collection.query(query_texts=[user_input], n_results=5)

# 2. Inject as context (not as answers)
style_context = "\n---\n".join(results["documents"][0])

# 3. Generate with personality prompt + style context
# The model should use these snippets as style reference, not copy them verbatim
```

## Pitfalls

- **Multi-speaker data muddies the signal.** Without speaker diarization (PyAnnote / WhisperX), 4-person podcast transcripts will mix everyone's voice. The clone will learn wrong mannerisms. **Stick to solo content.**
- **Too little data → generic imitation.** Aim for 30min-2h of solo speech minimum.
- **Too much data → parrot mode.** The model starts copying entire bits verbatim. Use smaller `n_results` (3-5) and lower temperature.
- **Controversy filter.** Decide upfront whether to include controversial/offensive statements. The clone will reproduce the person's full range — including bad takes.
- **Diarization dependency warning.** If multi-speaker content is unavoidable, use `pyannote.audio` or `whisperx` for speaker segmentation first.
- **Context window limit.** Personality data is consumed at query time. Keep injected chunks under 1500 chars to leave room for the model's own persona response.
- **Tone drift.** Without periodic RAG refresh, the AI will drift toward its default training tone. Always inject style context.
- **Gaali/slang tagging.** Store slang-heavy chunks with a dedicated metadata tag so the clone can retrieve them on roast/insult queries separately from casual conversation.

## Related Skills
- `chroma` — vector database operations and setup
- `youtube-content` — fetching YouTube transcripts
- `dspy` — advanced RAG pipeline automation
