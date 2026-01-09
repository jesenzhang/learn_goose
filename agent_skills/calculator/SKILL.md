---
name: calculator
description: Perform mathematical calculations accurately. Use when the user asks for math or stats.
allowed-tools: [calculate]
---

# Calculator

## Instructions
1. The user may ask natural language math questions (e.g., "what is 15% of 850").
2. Convert the request into a valid Python mathematical expression.
3. Use the `calculate` tool to get the result.
4. Do not try to do complex math in your head; always use the tool.

## Examples
User: "Calculate 25 * 40 / 2"
Assistant: (Calls calculate with expression="25 * 40 / 2")