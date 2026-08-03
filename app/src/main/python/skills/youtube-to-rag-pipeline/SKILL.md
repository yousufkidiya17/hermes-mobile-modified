---
name: youtube-to-rag-pipeline
description: "Build a RAG from YouTube transcripts for personality clones."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [RAG, YouTube, transcripts, personality-clone, vector-db, chroma]
    related_skills: [youtube-content, chroma]
---

# YouTube Transcript → RAG Pipeline

Build a searchable knowledge base from YouTube transcripts that captures a creator's speaking style, catchphrases, vocabulary, and personality — not just factual content.

## When to Use
- User wants to clone a YouTuber/creator's AI personality
- Building a RAG that captures tone, style, and catchphrases
- Learning RAG hands-on with real YouTube data

## Pipeline

```
YouTube URL → Transcript → Chunks → Embeddings → Vector DB → Query → Personality Response
```

## Step 1: Get Transcripts

Use `youtube-transcript-api`:

```bash
pip install youtube-transcript-api
python3 -c "
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript('VIDEO_ID')
for t in transcript:
    print(f'{t[\"start\"]}: {t[\"text\"]}')
"
```

Prefer **solo content** (comedy specials, monologues, solo vlogs) over multi-speaker videos.

## Step 2: Chunk & Organize

Split into 200-500 word semantic chunks. Organize by **style type**:

| Category | What It Captures |
|----------|-----------------|
| speaking_style | Hinglish mix, sentence rhythm, filler words |
| catchphrases | Signature phrases, repeated expressions |
| humor_style | Roast pattern, punchline structure |
| vocabulary | Unique words, slang, domain terms |

## Step 3: Store in Chroma

```python
import chromadb
client = chromadb.PersistentClient(path='./rag_db')
collection = client.create_collection(name='personality')
collection.add(documents=chunks, metadatas=[...], ids=[...])
```

## Step 4: Query

Query for style: "Kaise roast karta hai?", "Signature dialogue kya hai?"
The RAG returns relevant style chunks → inform the AI's response.

## Step 5: System Prompt Assembly

```
You are [PERSON]. Speak exactly like them:
- Mix Hindi/English
- Signature phrases: {extracted}
- Humor style: {extracted}
```

## Dependencies
- `youtube-transcript-api`
- `chromadb`
- `sentence-transformers`

## Pitfalls
- Multi-speaker videos need filtering — prefer solo content
- Transcripts miss delivery tone (sarcasm) — note it in metadata
- Focus on HOW they speak, not WHAT they say
