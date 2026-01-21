---
name: file-operations
description: Perform file operations like read, write, delete, and list directories
author: Goose Contributors
version: 1.0.0
tags:
  - file
  - io
  - filesystem
---

# File Operations Skill

This skill provides capabilities for working with files and directories in the filesystem.

## Available Tools

Use the following tools for file operations:

### Read File
Read the contents of a file at the specified path.

### Write File
Write content to a file at the specified path. Creates the file if it doesn't exist.

### List Directory
List all files and subdirectories in a given directory.

### Delete File
Delete a file at the specified path.

### Create Directory
Create a new directory at the specified path.

## Usage Examples

### Reading a file
```
Use the read_file tool to read configuration files, source code, or any text content.
```

### Writing to a file
```
Use the write_file tool to save output, create new files, or update existing content.
```

### Directory navigation
```
Use list_directory to explore the project structure and find relevant files.
```

## Best Practices

1. Always use absolute paths when possible
2. Check file existence before reading or writing
3. Handle errors gracefully with try-catch blocks
4. Use appropriate encoding (UTF-8 for text files)
5. Close file handles properly after use

## Security Considerations

- Validate file paths to prevent directory traversal attacks
- Check file permissions before reading sensitive data
- Be careful when writing to system directories
- Avoid executing files from untrusted sources
