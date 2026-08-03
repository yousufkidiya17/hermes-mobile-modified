# Memory Usage

Use the memory tools to remember and recall information across conversations.

Tools:
- `memory_set(key, value)` — save a fact for later
- `memory_get(key)` — recall a saved fact

When to use:
- User tells you a personal detail or preference (name, language, style)
- User asks you to remember something
- A fact will matter in future conversations

Best practices:
- Use short, meaningful keys (e.g. "user_name", "preferred_language")
- Store concise values
- Before answering a personal question, check memory_get first