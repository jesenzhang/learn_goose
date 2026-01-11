"""
Native Python code execution sandbox.

Provides local Python execution with AST-based security checks
and parameter injection in Coze style.
"""

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
    Local Python execution environment.

    Features:
    - AST static security checks
    - Coze-style parameter injection
    - Safe built-ins filtering
    - Timeout control
    """

    async def run_code(self, code: str, inputs: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        """
        Run Python code with safety checks.

        Args:
            code: Python code to execute
            inputs: Input parameters dictionary
            timeout: Maximum execution time in seconds

        Returns:
            Dictionary containing execution results

        Raises:
            RuntimeError: If execution fails or times out
        """
        # 1. Static security check
        self._validate_imports(code)

        # 2. Prepare sandbox environment (Globals)
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
            # Allow __import__ for import statements in code
            # (dangerous modules are blocked by _validate_imports)
            "__import__": __import__,
        }

        safe_globals = {
            "__builtins__": safe_builtins,
            "__name__": "__main__",
            "math": math,
            "random": random,
            "json": json,
            "datetime": datetime,
            "asyncio": asyncio  # Pre-inject asyncio
        }

        # 3. Wrap code (inject Args class)
        # Indent user code and place in _wrapper function
        indented_code = "\n".join(["    " + line for line in code.splitlines()])

        wrapped_code = f"""
async def _wrapper(params_dict):
    # Simulate Coze Args object
    class Args:
        def __init__(self, params):
            self.params = params

        def get(self, key, default=None):
            return self.params.get(key, default)

        def __getitem__(self, key):
            return self.params[key]

    args = Args(params_dict)

    # --- User code starts ---
{indented_code}
    # --- User code ends ---

    if 'main' in locals():
        return await main(args)
    else:
        raise ValueError("Code must define 'async def main(args):'")
"""
        local_scope = {}

        try:
            # 4. Execute code definition
            exec(wrapped_code, safe_globals, local_scope)

            entry_func = local_scope["_wrapper"]

            # 5. Run (with timeout)
            result = await asyncio.wait_for(entry_func(inputs), timeout=timeout)

            # 6. Format output
            if not isinstance(result, dict):
                return {"output": result}
            return result

        except asyncio.TimeoutError:
            raise RuntimeError(f"Code execution timed out after {timeout}s")
        except Exception as e:
            raise RuntimeError(f"Code Execution Error: {str(e)}")

    def _validate_imports(self, code: str):
        """
        Use AST parsing for strict security checks.
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
                # Check imports
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for name in node.names:
                            if name.name in DANGEROUS_MODULES:
                                raise ValueError(f"Security Error: Import of '{name.name}' is forbidden.")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module in DANGEROUS_MODULES:
                            raise ValueError(f"Security Error: Import from '{node.module}' is forbidden.")

                # Check function calls
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_FUNCTIONS:
                        raise ValueError(f"Security Error: Call to '{node.func.id}' is forbidden.")
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr in DANGEROUS_ATTRIBUTES:
                            raise ValueError(f"Security Error: Access to '{node.func.attr}' is forbidden.")
                        if isinstance(node.func.value, ast.Name) and node.func.value.id in DANGEROUS_MODULES:
                            raise ValueError(f"Security Error: Call to '{node.func.value.id}.{node.func.attr}' is forbidden.")

                # Check attribute access
                elif isinstance(node, ast.Attribute):
                    if node.attr in DANGEROUS_ATTRIBUTES:
                        raise ValueError(f"Security Error: Access to '{node.attr}' is forbidden.")

        except SyntaxError as e:
            raise ValueError(f"Syntax Error in code: {str(e)}")
        except Exception as e:
            raise ValueError(f"Security Error: {str(e)}")
