from typing import Any, Optional, Dict, List
import json

# ============================================================================
# Skill Implementation
# ============================================================================

def write_to_clipboard(key: str, value: Any, _state: Any = None) -> str:
    """
    Save data to the shared clipboard for other skills to use.
    
    Args:
        key: A unique string identifier for the data.
        value: The data to save (string, number, or JSON serializable object).
    
    Returns:
        A system message confirming the save or an error message.
    """
    # 1. 环境/状态检查 (Critical for Skills)
    if _state is None:
        return "Error: System state is missing. Cannot write to clipboard."
    
    # 兼容 _state 是对象(attr)或字典(dict)的情况
    memory = getattr(_state, 'shared_memory', None)
    if memory is None and isinstance(_state, dict):
        # 如果 _state 本身就是 dict，且没有 shared_memory 属性，尝试直接用 _state.get('shared_memory')
        # 或者假设 _state 本身就是内存容器。这里假设标准结构是 _state.shared_memory
        memory = _state.get('shared_memory')
    
    if memory is None:
        return "Error: 'shared_memory' not initialized in system state."

    # 2. 参数校验 (帮助 LLM 修正调用)
    if not key or not isinstance(key, str):
        return f"Error: Invalid key type. Expected a non-empty string, got {type(key).__name__}."
    
    if value is None:
        return "Error: Cannot save 'None' to clipboard."

    # 3. 执行写入
    try:
        memory[key] = value
        
        # 4. 返回友好的 Observation
        # 如果 value 太长，截断显示，避免污染 Context，但实际数据已完整保存
        val_str = str(value)
        preview = val_str[:100] + "..." if len(val_str) > 100 else val_str
        return f"System: Successfully saved data to clipboard under key '{key}'. Value preview: {preview}"
        
    except Exception as e:
        return f"Error: Failed to write to clipboard. Details: {str(e)}"


def read_from_clipboard(key: str, _state: Any = None) -> str:
    """
    Read data from the shared clipboard.
    
    Args:
        key: The string identifier used when saving the data.
        
    Returns:
        The data content string, or an error message with available keys if not found.
    """
    # 1. 环境检查
    if _state is None:
        return "Error: System state is missing. Cannot read from clipboard."

    memory = getattr(_state, 'shared_memory', None)
    if memory is None and isinstance(_state, dict):
        memory = _state.get('shared_memory')
        
    if memory is None:
        return "Error: 'shared_memory' is empty or not initialized."

    # 2. 参数校验
    if not key or not isinstance(key, str):
        return "Error: Key must be a non-empty string."

    # 3. 执行读取
    try:
        value = memory.get(key)
        
        # 4. 核心逻辑：处理“未找到”的情况
        if value is None:
            # 【关键优化】列出当前所有可用的 keys，帮助 LLM 自我纠错
            # 例如：用户想读 "sales_data"，但实际存的是 "sales_pdf_data"
            available_keys = list(memory.keys())
            keys_str = ", ".join(f"'{k}'" for k in available_keys)
            if not keys_str:
                keys_str = "(Clipboard is empty)"
            
            return f"Error: Key '{key}' not found in clipboard. Available keys are: {keys_str}"

        # 5. 返回结果
        # 如果是复杂对象，尝试转 JSON，否则转 str
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except:
                return str(value)
        
        return str(value)

    except Exception as e:
        return f"Error: An exception occurred while reading clipboard. Details: {str(e)}"