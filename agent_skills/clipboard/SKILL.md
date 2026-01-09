---
name: clipboard
type: global
description: A shared memory space. Use this to pass data between different skills.
allowed-tools: [write_to_clipboard, read_from_clipboard]
---

# Clipboard (Shared Memory)

## Instructions
1. When a skill produces important data (e.g., text from a PDF) that another skill will need, save it using `write_to_clipboard`.
2. When you need data produced by a previous skill, use `read_from_clipboard`.
3. Use descriptive keys (e.g., "sales_data_from_pdf", "final_sum").