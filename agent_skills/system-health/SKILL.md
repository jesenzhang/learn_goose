---
name: system-health
description: Retrieve system information, OS version, and resource usage. Use when user asks about server status or specs.
allowed-tools: [get_os_info, get_disk_usage]
---

# System Health Diagnostics

## Instructions
1. When asked about "status" or "specs", always start by calling `get_os_info`.
2. If the user asks about storage or disk space, use `get_disk_usage`.
3. Present the data in a clean, bulleted list.

## Examples
User: "What server is this?"
Assistant: (Calls get_os_info)