import os
import locale

def sanitize_path(target_path: str, base_dir: str = None) -> str:
    """
    [安全防御] 防止路径遍历攻击
    """
    # [修复] 统一变量名，这里之前把 base_dir 写成了 base_path
    if base_dir is None:
        base_dir = os.getcwd()
        
    abs_base = os.path.abspath(base_dir)
    abs_target = os.path.abspath(os.path.join(abs_base, target_path))
    
    if not os.path.commonpath([abs_base]) == os.path.commonpath([abs_base, abs_target]):
        raise ValueError(f"Access denied: Path '{target_path}' is outside '{base_dir}'")
        
    return abs_target

def truncate_output(output: str, max_chars: int = 20000) -> str:
    """
    [成本控制] 防止输出过长撑爆 Context
    """
    if len(output) <= max_chars:
        return output
    
    truncated_msg = f"\n... [Output truncated, showing last {max_chars} characters] ..."
    return truncated_msg + output[-max_chars:]

def decode_output(data: bytes) -> str:
    """
    [兼容性] 智能处理 Windows/Linux 编码
    """
    if not data:
        return ""
    
    # 尝试常见编码
    encodings = ['utf-8', locale.getpreferredencoding(), 'gbk', 'cp1252', 'latin-1']
    
    for enc in encodings:
        try:
            return data.decode(enc).strip()
        except (UnicodeDecodeError, TypeError):
            continue
            
    # 最后的手段
    return data.decode('utf-8', errors='replace').strip()