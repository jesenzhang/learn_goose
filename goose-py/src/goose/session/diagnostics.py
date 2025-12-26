# goose-py/diagnostics.py
import io
import json
import zipfile
import platform
import sys
from datetime import datetime
from typing import Any

async def generate_diagnostics(session_manager, session_id: str) -> bytes:
    """
    生成诊断 ZIP 包的二进制数据
    :param session_manager: SessionManager 实例
    :param session_id: 当前会话 ID
    """
    
    # 1. 准备系统信息
    system_info = (
        f"App Version: goose-py-0.1.0\n"
        f"Python Version: {sys.version}\n"
        f"OS: {platform.system()} {platform.release()}\n"
        f"Architecture: {platform.machine()}\n"
        f"Timestamp: {datetime.utcnow().isoformat()}\n"
    )

    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 2. 写入系统信息
        zf.writestr("system.txt", system_info)
        
        # 3. 导出 Session 数据 (Session.json)
        try:
            session = await session_manager.get_session(session_id)
            messages = await session_manager.get_storage().get_messages(session_id)
            
            export_data = {
                "session": session.model_dump(mode='json', by_alias=True),
                "messages": [m.model_dump(mode='json', by_alias=True) for m in messages]
            }
            zf.writestr("session.json", json.dumps(export_data, indent=2))
        except Exception as e:
            zf.writestr("session_error.txt", str(e))

        # 4. 模拟日志文件 (Goose 逻辑是读取 logs 目录，这里暂且留空或写入伪日志)
        zf.writestr("logs/app.log", "[INFO] Diagnostics generated.")

        # 5. 写入配置信息 (如果有)
        # zf.writestr("config.yaml", ...)

    buffer.seek(0)
    return buffer.getvalue()