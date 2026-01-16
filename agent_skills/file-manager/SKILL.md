---
name: file-manager
description: Advanced file operations. Supports handling large files via pagination and search.
allowed-tools: [list_directory, get_file_info, read_file, search_in_file, write_file]
---

# File Manager

## Capabilities
- Navigate directories (`list_directory`)
- Analyze file metadata (`get_file_info`)
- **Read Large Files**: Use pagination (`read_file` with `start_line`)
- **Search**: Find specific content without reading everything (`search_in_file`)
- Edit files: Overwrite (`mode='w'`) or Append (`mode='a'`)

## Safety & Best Practices
1. **Always Check Size**: Before reading a file, call `get_file_info` to see how many lines it has.
2. **Avoid Context Overflow**: 
   - If a file has < 100 lines, you can read it all at once.
   - If a file has > 100 lines, **DO NOT** read it all. Use `read_file(filename, start_line=1, max_lines=50)`.
3. **Use Search**: If you are looking for specific information (e.g., "error" in a log file), use `search_in_file` instead of reading page by page.
4. **Iterative Reading**: If you need to read more, look at the metadata in the previous `read_file` output and increment the `start_line`.

## Instruction Examples

**User:** "What's in the error log?"
**Assistant:**
1. Calls `get_file_info(filename="error.log")` -> Returns "Total Lines: 5000"
2. Thinking: "File is too big to read. I should search for 'error' or read the last few lines."
3. Calls `read_file(filename="error.log", start_line=4950, max_lines=50)` (To see the end)
   OR
   Calls `search_in_file(filename="error.log", keyword="Exception")`

**User:** "Add a new requirement to the readme."
**Assistant:**
1. Calls `read_file(filename="README.md")` to check context.
2. Calls `write_file(filename="README.md", content="\n- New requirement", mode="a")`