# opencoze/infra/sandbox/native.py

import asyncio
import math
import random
import json
import datetime
import ast
from typing import Dict, Any
from .base import ICodeSandbox

class NativeSandboxAdapter(ICodeSandbox):
    """
    本地 Python 执行环境 (Enhanced Native Execution)
    集成了 AST 静态安全检查和 Coze 风格的参数注入。
    """
    
    async def run_code(self, code: str, inputs: Dict, timeout: int = 30) -> Dict:
        # 1. 静态安全检查
        self._validate_imports(code)

        # 2. 准备沙箱环境 (Globals)
        safe_builtins = {
            "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
            "bytearray": bytearray, "bytes": bytes, "chr": chr, "dict": dict,
            "divmod": divmod, "enumerate": enumerate, "filter": filter,
            "float": float, "format": format, "frozenset": frozenset,
            "getattr": getattr, "hasattr": hasattr, "hash": hash, "hex": hex,
            "int": int, "isinstance": isinstance, "issubclass": issubclass,
            "iter": iter, "len": len, "list": list, "map": map, "max": max,
            "min": min, "next": next, "object": object, "oct": oct, "ord": ord,
            "pow": pow, "print": print, "range": range, "repr": repr,
            "reversed": reversed, "round": round, "set": set, "slice": slice,
            "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
            "type": type, "zip": zip, "Exception": Exception, "ValueError": ValueError,
            "__build_class__": __build_class__,
            "locals": locals,
            # [Fix] 恢复 __import__ 以支持代码中的 import 语句
            # 前提是 _validate_imports 已经拦截了危险模块名
            "__import__": __import__, 
        }

        safe_globals = {
            "__builtins__": safe_builtins,
            "__name__": "__main__",
            "math": math,
            "random": random,
            "json": json,
            "datetime": datetime,
            "asyncio": asyncio # 预注入 asyncio
        }
        
        
        # 3. 包装代码 (注入 Args 类)
        # 将用户代码缩进，放入 _wrapper 函数中
        indented_code = "\n".join(["    " + line for line in code.splitlines()])
        
        wrapped_code = f"""
async def _wrapper(params_dict):
    # 模拟 Coze 的 Args 对象
    class Args:
        def __init__(self, params):
            self.params = params
        
        def get(self, key, default=None):
            return self.params.get(key, default)
            
        def __getitem__(self, key):
            return self.params[key]

    args = Args(params_dict)
    
    # --- 用户代码开始 ---
{indented_code}
    # --- 用户代码结束 ---
    
    if 'main' in locals():
        return await main(args)
    else:
        raise ValueError("Code must define 'async def main(args):'")
"""
        local_scope = {}

        try:
            # 4. 执行代码定义
            exec(wrapped_code, safe_globals, local_scope)
            
            entry_func = local_scope["_wrapper"]
            
            # 5. 运行 (带超时)
            result = await asyncio.wait_for(entry_func(inputs), timeout=timeout)
            
            # 6. 格式化输出
            if not isinstance(result, dict):
                return {"output": result}
            return result

        except asyncio.TimeoutError:
            raise RuntimeError(f"Code execution timed out after {timeout}s")
        except Exception as e:
            raise RuntimeError(f"Code Execution Error: {str(e)}")

    def _validate_imports(self, code: str):
        """
        使用 AST 解析进行严格的安全检查
        """
        DANGEROUS_MODULES = {
            "os", "sys", "subprocess", "socket", "multiprocessing", "threading",
            "importlib", "shutil", "builtins", "ctypes", "pickle", "marshal",
            "eval", "exec", "compile", "open", "file", "input", "raw_input"
        }
        
        DANGEROUS_ATTRIBUTES = {
            "__init__", "__new__", "__del__", "__getattribute__", "__setattr__",
            "__delattr__", "__getitem__", "__setitem__", "__delitem__",
            "__call__", "__import__", "__globals__", "__locals__", "__dict__",
            "__class__", "__bases__", "__mro__", "__subclasses__", "__instancecheck__",
            "__subclasscheck__", "__dir__", "__sizeof__", "__reduce__", "__reduce_ex__",
            "__getstate__", "__setstate__"
        }
        
        DANGEROUS_FUNCTIONS = {
            "eval", "exec", "compile", "open", "__import__", "input", "raw_input"
        }
        
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for name in node.names:
                            if name.name in DANGEROUS_MODULES:
                                raise ValueError(f"Security Error: Import of '{name.name}' is forbidden.")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module in DANGEROUS_MODULES:
                            raise ValueError(f"Security Error: Import from '{node.module}' is forbidden.")
                
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_FUNCTIONS:
                        raise ValueError(f"Security Error: Call to '{node.func.id}' is forbidden.")
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr in DANGEROUS_ATTRIBUTES:
                            raise ValueError(f"Security Error: Access to '{node.func.attr}' is forbidden.")
                        if isinstance(node.func.value, ast.Name) and node.func.value.id in DANGEROUS_MODULES:
                            raise ValueError(f"Security Error: Call to '{node.func.value.id}.{node.func.attr}' is forbidden.")
                
                elif isinstance(node, ast.Attribute):
                    if node.attr in DANGEROUS_ATTRIBUTES:
                        raise ValueError(f"Security Error: Access to '{node.attr}' is forbidden.")
                        
        except SyntaxError as e:
            raise ValueError(f"Syntax Error in code: {str(e)}")
        except Exception as e:
            raise ValueError(f"Security Error: {str(e)}")