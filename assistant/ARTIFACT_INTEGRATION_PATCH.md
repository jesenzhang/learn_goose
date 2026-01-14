# Artifact Storage 集成补丁

将以下代码添加到 `src/assistant/core/agent.py` 中

## 1. 在 _format_and_emit_tool_result 中添加 Artifact Manager 支持

找到这行：
```python
async def _format_and_emit_tool_result_original(self, result: CallToolResult, state: AgentState) -> str:
```

替换为：
```python
async def _format_and_emit_tool_result(self, result: CallToolResult, state: AgentState) -> str:
    from .artifact_storage import get_manager

    artifact_mgr = get_manager()
    use_artifact_manager = artifact_mgr is not None and artifact_mgr.config.enabled

    # 如果启用 ArtifactManager，使用新逻辑
    if use_artifact_manager:
        return await self._emit_artifact_with_manager(result, state)

    # 否则回退到原始实现
    return await self._format_and_emit_tool_result_original(result, state)
```

## 2. 添加会话清理逻辑

在 MicroAgent 类中添加以下方法：

```python
async def end_session(self, session_id: str) -> None:
    """清理会话资源（包括 artifacts）"""
    from .artifact_storage import get_manager

    artifact_mgr = get_manager()
    if artifact_mgr and artifact_mgr.config.enabled:
        count = await artifact_mgr.cleanup_session(session_id=session_id)
        self.logger.info(f"Cleaned up {count} artifacts for session {session_id}")

    # ... 其他清理逻辑
```

## 3. 添加 API 端点方法（在 api/routes.py 中添加）

```python
# Artifact API 端点

from fastapi import HTTPException
from ..core.artifact_storage import get_manager

@router.get("/sessions/{session_id}/artifacts/{artifact_id}")
async def get_artifact(session_id: str, artifact_id: str):
    """获取 artifact 数据"""
    artifact_mgr = get_manager()
    if artifact_mgr is None:
        raise HTTPException(status_code=503, detail="Artifact manager not available")

    data = await artifact_mgr.load(
        session_id=session_id,
        artifact_id=artifact_id,
    )

    if data is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return {
        "id": artifact_id,
        "data": data,
    }
```
