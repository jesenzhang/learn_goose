import json
import re
import logging

logger = logging.getLogger(__name__)

def repair_and_parse_json(json_str: str) -> dict:
    """
    终极版 JSON 修复器。
    通过字符级状态机解决 LLM 常见的 "Double Quote Hell" 问题。
    """
    if not json_str:
        return {}

    # 1. 基础清洗 (Markdown & Whitespace)
    cleaned = re.sub(r"^```(?:json)?\s*", "", json_str, flags=re.IGNORECASE | re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # 2. 尝试直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. 提取最外层大括号 (解决 Extra Data 问题)
    # 使用非贪婪匹配 + 递归查找可能更好，这里用简单的栈计数法提取第一个完整对象
    extracted = _extract_first_json_object(cleaned)
    if extracted:
        cleaned = extracted

    # 4. 尝试直接解析提取后的内容
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 5. 字符级修复 (解决未转义引号问题)
    # 这是核心逻辑：{"k": "print("hello")"} -> {"k": "print(\"hello\")"}
    repaired = _escape_inner_quotes(cleaned)
    
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        # 如果还是失败，记录日志并抛出，让 Agent 看到原始错误
        logger.warning(f"JSON Repair failed: {e}. Raw: {json_str[:200]}...")
        raise e

def _extract_first_json_object(text: str) -> str:
    """提取第一个完整的 {...} 块"""
    stack = 0
    start_index = -1
    
    for i, char in enumerate(text):
        if char == '{':
            if stack == 0:
                start_index = i
            stack += 1
        elif char == '}':
            if stack > 0:
                stack -= 1
                if stack == 0:
                    return text[start_index : i+1]
    return text # 如果没找到配对的，返回原样试试

def _escape_inner_quotes(s: str) -> str:
    """
    智能转义逻辑：
    遍历字符串，识别 JSON 的 Key-Value 结构。
    当我们处于 Value 字符串内部时，如果遇到 " 且它看起来不像是字符串的结尾，
    就将其转义为 \"。
    """
    output = []
    in_string = False
    escape_next = False
    
    i = 0
    while i < len(s):
        char = s[i]
        
        if escape_next:
            output.append(char)
            escape_next = False
            i += 1
            continue
            
        if char == '\\':
            output.append(char)
            escape_next = True
            i += 1
            continue
            
        if char == '"':
            if not in_string:
                # 进入字符串 (Key 或 Value 的开始)
                in_string = True
                output.append(char)
            else:
                # 我们在字符串里遇到了引号。是结尾吗？
                # 检查下一个非空字符
                is_end_of_string = False
                j = i + 1
                while j < len(s) and s[j].isspace():
                    j += 1
                
                if j < len(s):
                    next_char = s[j]
                    # 如果后面是 : (Key结束), , (字段结束), } (对象结束), ] (数组结束)
                    # 那么这个引号大概率是合法的结束符
                    if next_char in {':', ',', '}', ']'}:
                        is_end_of_string = True
                
                if is_end_of_string:
                    in_string = False
                    output.append(char)
                else:
                    # 不是结尾，说明是内部引用！转义它！
                    # "print(" -> "print(\"
                    output.append('\\"') 
        else:
            output.append(char)
            
        i += 1
        
    return "".join(output)