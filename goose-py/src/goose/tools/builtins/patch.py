import aiofiles
import os
from pydantic import BaseModel, Field
from ..base import Tool
from ...conversation.message import CallToolResult, RawContent
from ..utils import sanitize_path

class PatchArgs(BaseModel):
    path: str = Field(..., description="The absolute or relative path to the file.")
    old_str: str = Field(..., description="The exact string to be replaced. Must be unique in the file.")
    new_str: str = Field(..., description="The new string to replace it with.")

class PatchFileTool(Tool):
    name = "developer__text_editor_str_replace"
    description = (
        "Replace a unique string in a file with a new string. "
        "Use this for targeted edits to avoid rewriting large files. "
        "The `old_str` must appear exactly once in the file."
    )
    args_schema = PatchArgs

    async def run(self, path: str, old_str: str, new_str: str) -> CallToolResult:
        try:
            # 1. 安全检查
            safe_path = sanitize_path(path)
            
            if not os.path.exists(safe_path):
                return CallToolResult.failure(f"File not found: {path}")

            # 2. 读取内容
            async with aiofiles.open(safe_path, 'r', encoding='utf-8') as f:
                content = await f.read()

            # 3. 验证唯一性 (这是 Patch 成功的关键)
            count = content.count(old_str)
            if count == 0:
                # 尝试通过忽略空白字符来模糊匹配（可选增强，这里先保持严格）
                return CallToolResult.failure(
                    f"Error: `old_str` not found in file. Please ensure whitespace and indentation match exactly."
                )
            if count > 1:
                return CallToolResult.failure(
                    f"Error: `old_str` found {count} times. Replacement must be unique. Please include more context in `old_str`."
                )

            # 4. 执行替换
            new_content = content.replace(old_str, new_str)

            # 5. 写回文件
            async with aiofiles.open(safe_path, 'w', encoding='utf-8') as f:
                await f.write(new_content)

            return CallToolResult.success([
                RawContent(text=f"Successfully replaced text in {path}")
            ])

        except Exception as e:
            return CallToolResult.failure(f"Patch Error: {str(e)}")