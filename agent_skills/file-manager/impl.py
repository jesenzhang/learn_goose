import os
import math

# 简单的安全限制，防止访问项目以外的目录
BASE_DIR = os.getcwd()
DEFAULT_CHUNK_SIZE = 50  # 默认每次读取50行
MAX_PREVIEW_SIZE = 2000 # 字符数安全上限

def _get_safe_path(filename: str):
    """Internal helper to ensure path safety."""
    target = os.path.abspath(os.path.join(BASE_DIR, filename))
    if not target.startswith(os.path.abspath(BASE_DIR)):
        raise ValueError("Access denied: Path is outside the base directory.")
    return target

def list_directory(path: str = "."):
    """List files in the specified directory with type indicators."""
    try:
        target = _get_safe_path(path)
        if not os.path.exists(target):
            return "Error: Directory not found."
            
        items = os.listdir(target)
        # 优化：区分文件和文件夹
        result = []
        for item in items:
            full_path = os.path.join(target, item)
            type_flag = "[DIR]" if os.path.isdir(full_path) else "[FILE]"
            result.append(f"{type_flag} {item}")
        return f"Contents of '{path}':\n" + "\n".join(result)
    except Exception as e:
        return f"Error: {str(e)}"

def get_file_info(filename: str):
    """
    Get metadata about a file (size, line count) without reading content.
    Use this BEFORE reading to check if a file is too large.
    """
    try:
        target = _get_safe_path(filename)
        if not os.path.exists(target):
            return "Error: File does not exist."
            
        stats = os.stat(target)
        file_size = stats.st_size
        
        # 快速统计行数
        with open(target, 'r', encoding='utf-8', errors='ignore') as f:
            line_count = sum(1 for _ in f)
            
        return (f"File: {filename}\n"
                f"Size: {file_size} bytes\n"
                f"Total Lines: {line_count}\n"
                f"Suggestion: Use read_file with start_line/max_lines if Total Lines > {DEFAULT_CHUNK_SIZE}.")
    except Exception as e:
        return f"Error getting info: {str(e)}"

def read_file(filename: str, start_line: int = 1, max_lines: int = DEFAULT_CHUNK_SIZE):
    """
    Read a specific range of lines from a file.
    Args:
        start_line: The line number to start reading from (1-based index).
        max_lines: The maximum number of lines to read.
    """
    try:
        target = _get_safe_path(filename)
        if not os.path.exists(target):
            return "Error: File does not exist."

        content_lines = []
        current_line = 0
        end_line = start_line + max_lines - 1
        total_lines = 0

        # 流式读取，防止内存溢出
        with open(target, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                current_line += 1
                total_lines = current_line # Keep tracking total
                
                if current_line >= start_line and current_line <= end_line:
                    content_lines.append(f"{current_line}: {line.rstrip()}")
                
                # 稍微多读一点以计算是否 EOF，但在大文件中不需要读完整个文件
                # 这里为了简单，我们让它读完统计总行数，或者你可以结合 get_file_info 使用
        
        result_text = "\n".join(content_lines)
        
        # 构造带有导航信息的返回
        footer = f"\n\n--- Metadata ---\nShowing lines {start_line} to {min(end_line, total_lines)} of {total_lines}."
        if total_lines > end_line:
            footer += f"\n[MORE CONTENT AVAILABLE]: Call read_file(filename='{filename}', start_line={end_line + 1}) to read next chunk."
        else:
            footer += "\n[End of File]"
            
        return result_text + footer

    except Exception as e:
        return f"Error reading file: {str(e)}"

def search_in_file(filename: str, keyword: str, context_lines: int = 2):
    """
    Search for a keyword in a file and return matching lines with context.
    Essential for analyzing large logs or datasets.
    """
    try:
        target = _get_safe_path(filename)
        results = []
        
        with open(target, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                snippet = "".join([f"{idx+1}: {l}" for idx, l in enumerate(lines[start:end], start=start)])
                results.append(f"--- Match at line {i+1} ---\n{snippet}")
                
                if len(results) >= 10: # Limit results
                    results.append("... [Too many matches, stopping search] ...")
                    break
        
        if not results:
            return f"No matches found for '{keyword}' in {filename}."
            
        return "\n".join(results)
    except Exception as e:
        return f"Error searching file: {str(e)}"

def write_file(filename: str, content: str, mode: str = "w"):
    """
    Write to a file. 
    Args:
        mode: 'w' for overwrite, 'a' for append.
    """
    try:
        target = _get_safe_path(filename)
        
        # 安全检查：只有 'w' 和 'a' 是允许的
        if mode not in ['w', 'a']:
            return "Error: Mode must be 'w' (overwrite) or 'a' (append)."

        with open(target, mode, encoding='utf-8') as f:
            f.write(content)
            
        action = "Overwritten" if mode == 'w' else "Appended to"
        return f"Success: {action} file '{filename}'."
    except Exception as e:
        return f"Error writing file: {str(e)}"