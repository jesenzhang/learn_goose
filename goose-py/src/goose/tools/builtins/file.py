import aiofiles
import os
from pydantic import BaseModel, Field
from ..base import Tool
from ...conversation.message import CallToolResult, RawContent
from ..utils import sanitize_path

# --- Write Tool ---

class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Path to file. Will be overwritten if exists.")
    content: str = Field(..., description="Full content to write.")

class WriteFileTool(Tool):
    name = "developer__text_editor_write"
    description = "Write full content to a file. Create directories if needed."
    args_schema = WriteFileArgs

    async def run(self, path: str, content: str) -> CallToolResult:
        try:
            # 1. 路径安全检查 (限制在当前工作目录)
            safe_path = sanitize_path(path)
            
            # 2. 自动创建父目录
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            
            # 3. 写入文件
            async with aiofiles.open(safe_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            return CallToolResult.success([
                RawContent(text=f"Successfully wrote {len(content)} characters to {path}")
            ])
        except ValueError as ve:
            return CallToolResult.failure(f"Security Error: {str(ve)}")
        except Exception as e:
            return CallToolResult.failure(f"Write Error: {str(e)}")

# --- Read Tool ---

class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Path to file to read.")

class ReadFileTool(Tool):
    name = "developer__text_editor_read"
    description = "Read file content."
    args_schema = ReadFileArgs

    async def run(self, path: str) -> CallToolResult:
        try:
            safe_path = sanitize_path(path)
            
            if not os.path.exists(safe_path):
                return CallToolResult.failure(f"File not found: {path}")
            
            if not os.path.isfile(safe_path):
                return CallToolResult.failure(f"Path is not a file: {path}")

            async with aiofiles.open(safe_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                
            return CallToolResult.success([RawContent(text=content)])
            
        except ValueError as ve:
            return CallToolResult.failure(f"Security Error: {str(ve)}")
        except UnicodeDecodeError:
            return CallToolResult.failure("Error: File is binary or not UTF-8 encoded.")
        except Exception as e:
            return CallToolResult.failure(f"Read Error: {str(e)}")