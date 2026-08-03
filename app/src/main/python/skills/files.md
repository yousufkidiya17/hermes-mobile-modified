# File Operations

Use file tools to read, write, and list files on the device.

Tools:
- `read_file(path)` — read a file's contents
- `write_file(path, content)` — create or overwrite a file
- `list_files(path)` — list directory contents

When to use:
- User asks you to create a note, script, or document
- User wants to check file contents
- User asks to organize or inspect files

Safety:
- Only write to paths the user asks about
- Confirm before overwriting important files
- Never touch system files