import os

# 简单的安全限制，防止访问项目以外的目录
BASE_DIR = os.getcwd()

def list_directory(path: str = "."):
    """List files in the specified directory."""
    try:
        target = os.path.join(BASE_DIR, path)
        items = os.listdir(target)
        return f"Files in '{path}': {', '.join(items)}"
    except Exception as e:
        return f"Error: {str(e)}"

def read_file(filename: str):
    """Read the content of a file."""
    try:
        target = os.path.join(BASE_DIR, filename)
        if not os.path.exists(target):
            return "Error: File does not exist."
        with open(target, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(filename: str, content: str):
    """Write content to a file. Overwrites if exists."""
    try:
        target = os.path.join(BASE_DIR, filename)
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: File '{filename}' saved."
    except Exception as e:
        return f"Error writing file: {str(e)}"