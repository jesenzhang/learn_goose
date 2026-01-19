---
name: calculator
description: >
  Advanced mathematical calculator. Handles arithmetic, trigonometry, statistics, and scientific calculations.
  Use this for ANY math request, from simple addition to data analysis.
allowed-tools: [calculate]
---

# Calculator

## Capabilities
- **Arithmetic**: +, -, *, /, ** (power)
- **Functions**: sqrt, log, ln, factorial (e.g., 5!)
- **Trigonometry**: sin, cos, tan (inputs in radians), degrees, radians
- **Statistics**: mean, median, stdev (standard deviation) for lists of numbers

## Instructions
1. **Analyze** the user's math request.
2. **Translate** natural language into a valid Python expression using available functions.
   - For lists of numbers (average, median), use lists `[1, 2, 3]`.
   - For "power", use `**` or `pow()`.
   - For "factorial", use `factorial()`.
3. **Execute** via `calculate`.

## Examples

**User**: "Calculate the square root of 144 plus 5 squared."
**Assistant**: (Thought: sqrt(144) + 5^2)
**Tool Call**: `calculate(expression="sqrt(144) + 5**2")`

**User**: "What is the average of 12, 15, 22, and 9?"
**Assistant**: (Thought: Calculate mean of a list)
**Tool Call**: `calculate(expression="mean([12, 15, 22, 9])")`

**User**: "Calculate 15% of 850"
**Assistant**: (Thought: 0.15 * 850)
**Tool Call**: `calculate(expression="850 * 0.15")`

**User**: "What is the sine of 30 degrees?"
**Assistant**: (Thought: sin takes radians, need to convert)
**Tool Call**: `calculate(expression="sin(radians(30))")`