import asyncio
import os
import time
from typing import Optional
from pydantic import BaseModel, Field
from ..base import Tool, ToolError
from ...conversation.message import CallToolResult, RawContent
from ..utils import decode_output, truncate_output
from ..registry import register_tool

class ShellArgs(BaseModel):
    command: str = Field(..., description="The shell command to execute. Non-interactive commands only.")
    working_dir: Optional[str] = Field(None, description="Directory to execute command in.")
    timeout: int = Field(60, description="Max execution time in seconds. Default 60s.")

@register_tool()
class ShellTool(Tool):
    name = "developer__shell"
    description = (
        "Execute a shell command. "
        "Use this to list files, run tests, or execute scripts. "
        "Output is truncated if too long. "
        "Non-interactive commands only (no sudo/npm init that requires input)."
    )
    args_schema = ShellArgs

    async def run(self, command: str, working_dir: Optional[str] = None, timeout: int = 60) -> CallToolResult:
        cwd = working_dir or os.getcwd()
        
        if not os.path.exists(cwd):
            return CallToolResult.failure(f"Directory not found: {cwd}")

        try:
            # 记录开始时间
            start_time = time.time()
            
            # 使用 Shell=True 允许使用管道符 | 和重定向 >
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            try:
                # 等待执行，带超时控制
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                # 超时强制杀掉进程
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                return CallToolResult.failure(f"Command timed out after {timeout} seconds.")

            # 解码输出
            stdout = decode_output(stdout_bytes)
            stderr = decode_output(stderr_bytes)
            
            # 组合输出 (Claude Code 风格：合并流以便模型能看到错误上下文)
            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr}")
            
            full_output = "\n".join(output_parts)
            
            if not full_output:
                full_output = "(Command executed successfully with no output)"
            else:
                # 执行截断保护
                full_output = truncate_output(full_output)

            # 附加元数据信息，帮助 Agent 理解上下文
            duration = time.time() - start_time
            exit_code = process.returncode
            meta_info = f"\n[Exit Code: {exit_code}, Duration: {duration:.2f}s, CWD: {cwd}]"
            
            # 即使 exit_code != 0，也视为工具调用成功（只是命令失败），让 Agent 看到 stderr 去修复
            result_text = full_output + meta_info
            
            return CallToolResult.success([RawContent(text=result_text)])

        except Exception as e:
            return CallToolResult.failure(f"System Error: {str(e)}")