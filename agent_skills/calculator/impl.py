import math

def calculate(expression: str):
    """
    Evaluates a mathematical expression string.
    Supported: +, -, *, /, power (**), sqrt(), etc.
    """
    # 安全起见，只允许受限的命名空间
    allowed_names = {
        "math": math,
        "sqrt": math.sqrt,
        "pow": math.pow,
        "abs": abs,
        "round": round
    }
    
    try:
        # ⚠️ 注意：eval 在生产环境有风险，这里仅做演示
        # 实际生产应使用 numexpr 或 ast.literal_eval
        result = eval(expression, {"__builtins__": None}, allowed_names)
        return f"Result: {result}"
    except Exception as e:
        return f"Calculation Error: {str(e)}"