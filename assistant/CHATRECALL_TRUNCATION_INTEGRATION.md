# ChatRecall 和 Truncation 集成指南

本文档说明如何在 Assistant 项目中使用 ChatRecall 和 Truncation 功能。

## 功能概述

### ChatRecall (上下文召回)
- 搜索历史会话中的消息
- 加载特定会话的摘要（首尾消息）
- 基于日期范围过滤会话
- 支持模糊匹配和相似度评分

### Truncation (上下文压缩)
- 自动检测上下文使用情况
- LLM 基础的消息摘要和压缩
- 渐进式工具响应移除
- 上下文预算跟踪

## 配置

在 `assistant_config.yaml` 中添加配置：

```yaml
# ================= 上下文召回配置 =================
chatrecall:
  enabled: true
  max_results: 10
  max_session_messages: 3
  min_similarity: 0.3

# ================= 上下文压缩配置 =================
truncation:
  enabled: true
  threshold: 0.8              # 80% 触发压缩
  auto_compact: true          # 自动压缩
  max_messages_before_compact: 50
  keep_recent_messages: 5     # 保留最近N条消息
  check_interval: 5           # 每N条消息检查一次
```

## 使用方式

### 1. ChatRecall 使用示例

```python
from assistant.chatrecall import ChatRecall, ChatRecallConfig, create_chat_recall

# 定义会话查询函数
async def query_sessions(session_id=None):
    # 从数据库查询会话数据
    # 返回格式: {session_id: [{"role": "user", "content": "..."}, ...]}
    if session_id:
        return await db.get_session(session_id)
    else:
        return await db.list_all_sessions()

# 创建 ChatRecall 实例
config = ChatRecallConfig(
    max_results=10,
    min_similarity=0.3
)
recall = ChatRecall(
    session_query_func=query_sessions,
    config=config
)

# 搜索历史会话
results = await recall.search(
    query="青铜器",
    limit=5,
    after_date="2026-01-01",
    before_date="2026-01-31"
)

for result in results:
    print(f"Session: {result.session_id}, Score: {result.score}")
    for msg in result.messages:
        print(f"  [{msg['role']}] {msg['content']}")
```

### 2. Truncation 使用示例

```python
from assistant.truncation import (
    TruncationManager, TruncationConfig,
    create_truncation_manager, create_token_counter
)

# 创建 Truncation 管理器
config = TruncationConfig(
    threshold=0.8,
    auto_compact=True,
    keep_recent_messages=5
)

truncation_manager = TruncationManager(
    provider=llm_provider,  # BaseLLM 实例
    config=config
)

# 检查并压缩消息
messages = [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    # ... 更多消息
]

system_prompt = "You are a helpful assistant."

compacted, usage_info = await truncation_manager.check_and_compact(
    messages=messages,
    system_prompt=system_prompt
)

if compacted:
    print("Messages were compacted!")
    print(f"Usage: {usage_info}")
```

### 3. 与 Conversation 集成

```python
from assistant.truncation import TruncationManager, TruncationConfig
from assistant.truncation.conversation_integration import
ConversationTruncationMixin

# 创建支持 Truncation 的 Conversation 类
class EnhancedConversation(ConversationTruncationMixin, Conversation):
    pass

# 创建 Conversation 实例
conv = EnhancedConversation.empty()

# 设置 Truncation 管理器
truncation_manager = TruncationManager(provider=llm_provider)
conv.set_truncation_manager(truncation_manager)

# 添加消息
conv.push(Message.user("Hello"))
conv.push(Message.assistant("Hi there!"))
# ... 添加更多消息

# 在发送给 LLM 前，检查并应用压缩
system_prompt = "You are a helpful assistant."
await conv.check_and_apply_truncation(system_prompt=system_prompt)

# 获取用于 LLM 的消息
messages_for_llm = conv.for_llm()
```

### 4. 在 MicroAgent 中集成

```python
# 在 MicroAgent.__init__ 中初始化
if self.config.truncation.enabled:
    from assistant.truncation import TruncationManager, TruncationConfig

    truncation_config = TruncationConfig(
        enabled=self.config.truncation.enabled,
        threshold=self.config.truncation.threshold,
        auto_compact=self.config.truncation.auto_compact,
        max_messages_before_compact=self.config.truncation.max_messages_before_compact,
        keep_recent_messages=self.config.truncation.keep_recent_messages,
        check_interval=self.config.truncation.check_interval,
    )
    self.truncation_manager = TruncationManager(
        provider=self.current_generation.llm,
        config=truncation_config
    )
else:
    self.truncation_manager = None

# 在处理会话时应用 Truncation
async def process_conversation(session_id: int):
    conv = await self._load_conversation(session_id)

    # 设置 Truncation 管理器
    if self.truncation_manager:
        conv.set_truncation_manager(self.truncation_manager)

        # 获取系统提示词
        system_prompt = self.current_generation.config.agent.system_template

        # 检查并应用压缩
        await conv.check_and_apply_truncation(system_prompt=system_prompt)

    # 获取用于 LLM 的消息
    messages = conv.for_llm()

    # ... 继续处理
```

## API 参考

### ChatRecall

#### ChatRecallConfig
```python
ChatRecallConfig(
    max_results: int = 10,              # 最大搜索结果数
    max_session_messages: int = 3,       # 每个会话返回的消息数
    min_similarity: float = 0.3,        # 最小相似度阈值
    enabled: bool = True                 # 是否启用
)
```

#### ChatRecall 方法

```python
# 搜索历史会话
await recall.search(
    query: str,                        # 搜索关键词
    limit: int = 10,                   # 最大结果数
    after_date: Optional[str] = None,   # 开始日期
    before_date: Optional[str] = None   # 结束日期
) -> List[ChatRecallResult]

# 加载特定会话摘要
await recall.load_session(
    session_id: str
) -> Optional[SessionSummary]

# 通用回忆接口
await recall.recall(
    query: Optional[str] = None,        # 搜索模式
    session_id: Optional[str] = None,   # 加载模式
    limit: int = 10,
    after_date: Optional[str] = None,
    before_date: Optional[str] = None
) -> Dict[str, Any]
```

### Truncation

#### TruncationConfig
```python
TruncationConfig(
    enabled: bool = True,                    # 是否启用
    threshold: float = 0.8,                  # 压缩阈值（0-1）
    auto_compact: bool = True,               # 自动压缩
    max_messages_before_compact: int = 50,    # 硬限制
    keep_recent_messages: int = 5,            # 保留最近消息数
    check_interval: int = 5                   # 检查间隔
)
```

#### TruncationManager 方法

```python
# 检查并压缩
await manager.check_and_compact(
    messages: List[Dict[str, Any]],
    system_prompt: str
) -> Tuple[bool, Dict[str, Any]]

# 估算上下文使用
manager.estimate_context_usage(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    system_prompt: str
) -> Dict[str, Any]

# 获取统计信息
manager.get_stats() -> Dict[str, Any]

# 更新配置
manager.update_config(**kwargs)
```

## 注意事项

1. **TikToken 依赖**: Truncation 需要 `tiktoken` 包来准确计算 token 数量。如果未安装，将使用粗略估算。

2. **LLM 要求**: Truncation 需要一个支持文本生成的 LLM provider 来执行消息摘要。

3. **性能考虑**:
   - ChatRecall 在大量会话时可能较慢，建议使用索引或缓存
   - Truncation 的摘要生成需要额外的 LLM 调用

4. **配置调优**:
   - `threshold` 太高可能导致压缩不及时
   - `keep_recent_messages` 太少可能丢失重要上下文
   - `check_interval` 影响检查频率

5. **线程安全**: TruncationManager 使用异步锁保证线程安全。

## 故障排除

### 压缩未触发
- 检查 `truncation.enabled` 是否为 `true`
- 检查 `threshold` 设置是否合理
- 查看日志中的上下文使用情况

### ChatRecall 返回空结果
- 检查会话查询函数是否正确实现
- 检查 `min_similarity` 设置是否过高
- 查看日志中的搜索过程

### Token 计算不准确
- 确保已安装 `tiktoken`: `pip install tiktoken`
- 检查模型名称是否正确
