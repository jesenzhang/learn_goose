import os
import argparse
import fnmatch

# 默认忽略的目录
DEFAULT_IGNORE_DIRS = {
    '.git', '.idea', '.vscode', '__pycache__', 'node_modules', 
    'venv', '.env', 'dist', 'build', 'migrations', 'static/images',
    'opencoze.egg-info', 'docs', 'tests', 'examples'
}

# 默认忽略的文件后缀 (二进制文件或无关文件)
DEFAULT_IGNORE_EXTS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', 
    '.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe', 
    '.zip', '.tar', '.gz', '.pdf', '.lock', '.DS_Store',
    '.log', '.tmp', '.swp', '.swo', '.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe',
    '.md'
}

# 默认忽略的具体文件名
DEFAULT_IGNORE_FILES = {
    'package-lock.json', 'yarn.lock', 'poetry.lock'
}

def is_ignored(path, base_name, ignore_patterns):
    """检查文件或目录是否应该被忽略"""
    # 1. 检查默认忽略目录/文件
    if base_name in DEFAULT_IGNORE_DIRS or base_name in DEFAULT_IGNORE_FILES:
        return True
    
    # 2. 检查后缀
    _, ext = os.path.splitext(base_name)
    if ext.lower() in DEFAULT_IGNORE_EXTS:
        return True

    # 3. 检查用户自定义的 glob 模式 (例如 *.log)
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(base_name, pattern):
            return True
    
    return False

def generate_tree(root_path, ignore_patterns):
    """生成目录树字符串"""
    tree_str = f"Project Structure ({os.path.basename(os.path.abspath(root_path))}):\n"
    
    for root, dirs, files in os.walk(root_path):
        # 修改 dirs 列表以原地跳过忽略的目录
        dirs[:] = [d for d in dirs if not is_ignored(os.path.join(root, d), d, ignore_patterns)]
        files = [f for f in files if not is_ignored(os.path.join(root, f), f, ignore_patterns)]
        
        level = root.replace(root_path, '').count(os.sep)
        indent = ' ' * 4 * (level)
        subindent = ' ' * 4 * (level + 1)
        
        if root != root_path:
            tree_str += f"{indent}- {os.path.basename(root)}/\n"
            
        for f in files:
            # 如果是根目录，直接缩进；否则再缩进一级
            curr_indent = subindent if root != root_path else indent + '- '
            prefix = '- ' if root == root_path else ''
            tree_str += f"{curr_indent}{prefix}{f}\n"
            
    return tree_str

def get_file_content(file_path):
    """读取文件内容，处理编码错误"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # 尝试其他编码或直接跳过
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()
        except:
            return "[Binary or Non-text file content omitted]"
    except Exception as e:
        return f"[Error reading file: {str(e)}]"

def main():
    parser = argparse.ArgumentParser(description="将项目文件整合成一个 Markdown 文件供 LLM 阅读。")
    parser.add_argument("-s","--source_dir", help="项目的根目录路径")
    parser.add_argument("-o", "--output", default="project_context.md", help="输出的 Markdown 文件名 (默认: project_context.md)")
    parser.add_argument("-i", "--ignore", nargs='+', default=[], help="额外的忽略模式 (例如: *.log temp*)")
    
    args = parser.parse_args()
    
    source_dir = args.source_dir
    output_file = args.output
    ignore_patterns = args.ignore

    if not os.path.exists(source_dir):
        print(f"错误: 目录 '{source_dir}' 不存在。")
        return

    print(f"正在扫描目录: {source_dir} ...")

    with open(output_file, 'w', encoding='utf-8') as out:
        # 1. 写入头部提示
        out.write("# Project Context\n\n")
        out.write("This document contains the file structure and content of the project.\n\n")
        
        # 2. 写入目录树
        print("正在生成目录结构树...")
        tree = generate_tree(source_dir, ignore_patterns)
        out.write("## 1. Project Structure\n\n")
        out.write("```text\n")
        out.write(tree)
        out.write("```\n\n")
        
        # 3. 遍历并写入文件内容
        print("正在合并文件内容...")
        out.write("## 2. File Contents\n\n")
        
        file_count = 0
        for root, dirs, files in os.walk(source_dir):
            # 过滤目录
            dirs[:] = [d for d in dirs if not is_ignored(os.path.join(root, d), d, ignore_patterns)]
            
            for file in files:
                if is_ignored(os.path.join(root, file), file, ignore_patterns):
                    continue
                
                file_path = os.path.join(root, file)
                # 获取相对路径作为标题
                rel_path = os.path.relpath(file_path, source_dir)
                
                # 获取文件扩展名用于 markdown 代码块高亮
                _, ext = os.path.splitext(file)
                lang = ext.lstrip('.') if ext else 'text'
                
                content = get_file_content(file_path)
                
                # 写入 Markdown
                out.write(f"### File: `{rel_path}`\n\n")
                out.write(f"```{lang}\n")
                out.write(content)
                out.write("\n```\n\n")
                out.write("---\n\n")
                
                file_count += 1
                print(f"已处理: {rel_path}")

    print(f"\n完成! 已将 {file_count} 个文件整合到 '{output_file}'。")

if __name__ == "__main__":
    main()