---
name: clipboard
type: global
description: A volatile shared memory space for persisting data across different conversation turns or agent steps. Use this to pass intermediate results (e.g., scraped content, analysis summaries) between skills.
allowed-tools: [write_to_clipboard, read_from_clipboard]
---

# Clipboard (Shared Memory)

This skill allows you to store and retrieve data in a global shared memory. It is the primary mechanism for passing information from one step of a task to the next, or between different agents.

## Capabilities
- **Persist Data**: Save strings, numbers, lists, or dictionaries.
- **Retrieve Data**: Access previously saved data using unique keys.
- **Error Recovery**: Discover available keys if a specific key lookup fails.

## Tool Usage Guide

### 1. `write_to_clipboard(key: str, value: Any)`
Use this to save important outputs that will be needed later.
- **Key Naming Strategy**: Use descriptive, snake_case keys that clearly indicate the content's origin and type.
  - ❌ Bad: `data`, `temp`, `info`
  - ✅ Good: `pdf_extraction_result`, `weather_api_response`, `user_profile_summary`
- **Value Storage**: You can store complex objects (JSON/Dict) directly. Do not stringify JSON manually unless necessary; the tool handles object storage.

### 2. `read_from_clipboard(key: str)`
Use this to fetch data saved by previous steps.
- **Error Handling**: If the tool returns an error saying "Key not found", it will usually list **"Available keys"**. You MUST read this list and correct your key in the next turn.

## Operational Rules (Instructions)

1.  **Immediate Persistence**: As soon as you generate a valuable result (e.g., after a long search or calculation), save it to the clipboard immediately to prevent data loss.
2.  **Context Over Memory**: Do not rely on your conversation history context window for large datasets. Write them to the clipboard and read them only when necessary.
3.  **Check Before Hallucinating**: If you are unsure about a specific data point (e.g., a phone number derived 3 steps ago), read it from the clipboard instead of guessing.

## Examples

**Scenario 1: Passing data between steps**
> User: "Analyze the competitors of Company X and summarize their pricing."

*Step 1 (Search Agent)*:
```python
# ... performs search ...
write_to_clipboard(key="company_x_competitors_raw", value=search_results_dict)
```

*Step 2 (Analysis Agent)*:
```python
raw_data = read_from_clipboard(key="company_x_competitors_raw")
# ... performs analysis ...
```

**Scenario 2: Recovering from a wrong key Agent**
>  read_from_clipboard(key="users_list") 
> 
>  System: "Error: Key 'users_list' not found. Available keys are: 'user_list_v2', 'session_id'."
> 
> Agent: (Self-Correction) read_from_clipboard(key="user_list_v2")
