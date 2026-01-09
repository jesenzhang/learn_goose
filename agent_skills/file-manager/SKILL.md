---
name: file-manager
description: Read, write, and list files on the local filesystem. Use for file operations.
allowed-tools: [list_directory, read_file, write_file]
---

# File Manager

## Safety Rules
- **Never overwrite a file** without reading it first or asking for confirmation, unless explicitly instructed to "overwrite".
- Do not access system files outside the current directory.

## Instructions
1. To explore, use `list_directory` first.
2. To edit a file, first `read_file` to understand the context, then `write_file`.
3. If an error occurs (e.g., file not found), report it clearly to the user.

## Examples
User: "Create a todo list."
Assistant: (Calls write_file with filename="todo.txt")