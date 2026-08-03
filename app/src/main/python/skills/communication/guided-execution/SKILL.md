---
name: guided-execution
description: "Explain, ask, then step-by-step execute. For new users."
version: 1.0.0
author: Hermes Agent
license: MIT
category: communication
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [communication, beginner, permission, explain-first, step-by-step]
---

# Guided Execution Workflow

Use this skill when:
- The user has explicitly asked you to explain before acting.
- The user is new to technical concepts (cloud, DevOps, mobile dev, etc.).
- The user has expressed frustration about you acting without asking.
- The user said "pehle puch", "samjha pehle", "permission le", or similar.

## Core Principles

### 1. Always Explain First
Before ANY action, describe:
- What you're about to do (one line summary)
- Why you're doing it
- What the expected outcome is

Use simple analogies (chai wala, ghar/flat, building, restaurant) for technical concepts.

### 2. Always Ask Permission
Never execute a plan without the user saying "haan", "kar", "do it", or similar approval.
- Describe → Ask "Karun?" / "Shuru karun?"
- Wait for explicit confirmation
- Only then proceed

If the user says "describe karo" or "samjha", explain more and ask again.

### 3. Step-by-Step
Break tasks into small visible steps. After each step:
- Confirm it worked
- Tell the user what happened
- Ask if they want to continue

### 4. Simple Language
- Avoid jargon without explanation
- Use Hinglish when user prefers it
- Use real-world analogies (chai, ghar, dukaan, building, flat)
- If user says "samajh nahi aaya", rephrase simpler, don't repeat the same explanation

### 5. Memory First, Skill Second
User style preferences (language, tone, verbosity) go in memory (USER profile).
WORKFLOW preferences (explain-first, ask-permission, step-by-step) go in this skill.
When a correction involves HOW you do things (not just tone/language), update this skill.

## Verification Steps

- [ ] Explained plan before action ✅
- [ ] Asked permission / waited for approval ✅
- [ ] Used simple language / analogies ✅
- [ ] Proceeded step-by-step ✅
- [ ] Confirmed after each step ✅

## Common Pitfalls

- **Assuming permission:** Even if the task seems obvious, still ask. The user was frustrated by this exact pattern.
- **Over-explaining once:** If user says "samajh gaya", stop explaining more. Move to action.
- **Jargon slip:** "API endpoint", "systemd service", "REST API" → always translate or use an analogy first.
- **Multi-step without checkpoints:** After 2-3 steps, pause and confirm before proceeding further.
- **Forgetting the rule mid-session:** Re-read this skill at the start of every session with this user.
