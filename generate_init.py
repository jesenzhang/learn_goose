import os
import ast
import sys
import glob

def get_public_symbols(file_path):
    """
    解析 python 文件，返回该文件应该导出的符号列表。
    优先查找 __all__ 定义，如果没找到，则查找所有非下划线开头的类和函数。
    """
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError:
            print(f"Warning: Syntax error in {file_path}, skipping.")
            return []

    exported_symbols = []
    has_all = False

    # 1. 尝试寻找 __all__ 定义
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    # 找到了 __all__ = [...]
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        has_all = True
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant):  # Python 3.8+
                                exported_symbols.append(elt.value)
                            elif isinstance(elt, ast.Str):     # Python < 3.8
                                exported_symbols.append(elt.s)
    
    # 2. 如果没有定义 __all__，则提取所有顶层的 Class 和 Function
    if not has_all:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    exported_symbols.append(node.name)
            # 如果你也想包含全局变量，可以放开下面的注释，但通常不建议自动导出变量
            # elif isinstance(node, ast.Assign):
            #     for target in node.targets:
            #         if isinstance(target, ast.Name) and not target.id.startswith("_"):
            #             exported_symbols.append(target.id)

    return exported_symbols

def generate_init(package_dir):
    """
    在指定目录生成 __init__.py
    """
    if not os.path.isdir(package_dir):
        print(f"Error: {package_dir} is not a directory.")
        return

    init_path = os.path.join(package_dir, "__init__.py")
    
    # 扫描目录下所有的 .py 文件
    modules = glob.glob(os.path.join(package_dir, "*.py"))
    
    imports_map = {} # { module_name: [ClassA, ClassB] }
    all_exports = []

    print(f"Scanning package: {package_dir}")

    for module_path in modules:
        filename = os.path.basename(module_path)
        
        # 跳过 __init__.py 和 setup.py 等
        if filename == "__init__.py" or filename.startswith("setup"):
            continue
            
        module_name = filename[:-3] # 去掉 .py
        
        symbols = get_public_symbols(module_path)
        if symbols:
            imports_map[module_name] = sorted(symbols)
            all_exports.extend(symbols)
            print(f"  - {filename}: Found {len(symbols)} symbols {symbols}")
        else:
            print(f"  - {filename}: No public symbols found.")

    # 开始生成内容
    lines = []
    lines.append("# Auto-generated __init__.py")
    lines.append("")
    
    # 生成 import 语句
    for mod, symbols in sorted(imports_map.items()):
        # 使用相对导入: from .module import Class
        imports_list = ',\n'.join(f'    {obj}' for obj in sorted(symbols)) + ','
        # 2. 构造使用括号和换行的完整 from...import 语句
        formatted_import = (
            f"from .{mod} import (\n"
            f"{imports_list}\n"
            f")"
        )
        lines.append(formatted_import)
        
        # symbol_str = ", ".join(symbols)
        # lines.append(f"from .{mod} import {symbol_str}")

    lines.append("")
    
    # 生成 __all__
    # 对 export 列表去重并排序
    all_exports = sorted(list(set(all_exports)))
    
    lines.append("__all__ = [")
    for symbol in all_exports:
        lines.append(f"    '{symbol}',")
    lines.append("]")
    lines.append("")

    # 写入文件
    with open(init_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"\nSuccessfully generated {init_path} with {len(all_exports)} exported symbols.")

if __name__ == "__main__":
    # 使用方法: python generate_init.py <package_path>
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    generate_init(target_dir)