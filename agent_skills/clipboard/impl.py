# 这里我们需要一种方式访问当前的 state。
# 在 MicroAgent 的 _exec_tool_func 中，我们需要把 state 传进来，或者使用闭包/ContextVar。
# 为了简单演示，假设 MicroAgent 会在调用时注入 state。

def write_to_clipboard(key: str, value: str, _state=None):
    """
    Save data to the shared clipboard for other skills to use.
    """
    if _state:
        _state.shared_memory[key] = value
        return f"System: Saved to clipboard under key '{key}'."
    return "Error: State context missing."

def read_from_clipboard(key: str, _state=None):
    """
    Read data from the shared clipboard.
    """
    if _state:
        val = _state.shared_memory.get(key)
        if val:
            return f"Clipboard['{key}']: {val}"
        return f"Clipboard['{key}'] is empty."
    return "Error: State context missing."