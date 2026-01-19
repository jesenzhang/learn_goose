import math
import statistics
import re

def calculate(expression: str) -> str:
    """
    Evaluates a complex mathematical expression.
    Supports:
    - Basic: +, -, *, /, ** (power)
    - Constants: pi, e
    - Math: sqrt, log, log10, sin, cos, tan, factorial, degrees, radians
    - Stats: mean, median, stdev, variance (input list, e.g., mean([1,2,3]))
    """
    # 1. 预处理：清洗和修正 LLM 常见的语法错误
    # 移除 'calculate' 前缀（如果 LLM 不小心带上了）
    raw_expr = expression.strip()
    if raw_expr.lower().startswith("calculate"):
        raw_expr = raw_expr[9:].strip()
    
    # 将自然语言习惯的 '^' (异或) 替换为 Python 的幂运算 '**'
    # 注意：这假设用户不会在计算器里做位运算，符合绝大多数场景
    expr = raw_expr.replace("^", "**")
    
    # 替换自然语言中的乘号 'x' (如果它两边是数字或空格)
    expr = expr.replace("×", "*")

    # 2. 安全检查 (Guardrails)
    # 禁止下划线（防止访问 __import__ 等内部属性）
    # 禁止 import, exec, eval, lambda, open 等关键字
    dangerous_patterns = [r"__", r"import", r"exec", r"eval", r"open", r"lambda", r"sys", r"os"]
    if any(re.search(p, expr) for p in dangerous_patterns):
        return "Error: Security alert. Unsafe expression detected."

    # 3. 构建丰富的数学命名空间
    allowed_names = {
        # 基础常量
        "pi": math.pi,
        "e": math.e,
        
        # 基础运算
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": math.pow,
        "sqrt": math.sqrt,
        
        # 进阶数学
        "floor": math.floor,
        "ceil": math.ceil,
        "factorial": math.factorial, # 阶乘 5! -> factorial(5)
        "log": math.log,   # 自然对数
        "log10": math.log10,
        "exp": math.exp,
        
        # 三角函数
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "degrees": math.degrees, # 弧度转角度
        "radians": math.radians, # 角度转弧度
        
        # 统计函数 (支持列表输入)
        "mean": statistics.mean,     # 平均值
        "median": statistics.median, # 中位数
        "mode": statistics.mode,     # 众数
        "stdev": statistics.stdev,   # 标准差
        "variance": statistics.variance,
        
        # 命名空间别名 (Alias)
        "average": statistics.mean,
        "ln": math.log,
    }

    try:
        # 4. 执行计算
        # 使用 eval，但在严格受限的 env 中运行
        result = eval(expr, {"__builtins__": None}, allowed_names)
        
        # 5. 格式化输出
        # 如果是浮点数，保留一定精度，避免 0.1 + 0.2 = 0.30000000000000004
        if isinstance(result, float):
            return f"Result: {result:.6g}" # 6位有效数字
        
        return f"Result: {result}"

    except SyntaxError:
        return f"Error: Invalid syntax in expression '{raw_expr}'."
    except ZeroDivisionError:
        return "Error: Division by zero."
    except Exception as e:
        return f"Calculation Error: {str(e)}"