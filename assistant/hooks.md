Hook 系统优化总结

  1. 增强的 Hook 基础架构 (base.py)

  核心组件:
  - HookAction - 枚举类型，定义 5 种动作：CONTINUE, INTERCEPT, MODIFY, SKIP, RETRY
  - HookResult - 增强的结果类，支持多种操作和数据流动
  - HookContext - Hook 上下文，支持在 Hooks 之间传递共享数据
  - HookConfig - Hook 配置模型
  - AgentHook - 基类，定义完整的 Hook 生命周期点

  完整的 Hook 生命周期:
  # 请求生命周期
  on_request_start()    # 请求开始
  on_request_end()      # 请求结束

  # 输入处理
  on_user_input()       # 核心点 - FAQ、敏感词过滤等
  on_input_validated()  # 输入验证后

  # 意图识别
  on_intent_detect_start()  # 意图识别开始
  on_intent_detected()      # 意图识别后

  # 工具执行
  on_tool_start()       # 工具执行前
  on_tool_end()         # 工具执行后
  on_tool_error()       # 工具错误

  # 响应生成
  on_response_generate()   # 响应生成前
  on_response_generated()  # 响应生成后

  # 错误处理
  on_error()            # 全局错误处理

  2. Hook 管理器 (manager.py)

  核心功能:
  - HookRegistry - Hook 类注册表，支持动态创建
  - HookConfigLoader - 从配置文件加载
  - HookManager - Pipeline 执行引擎

  Pipeline 执行流程:
  用户输入
    ↓
  创建 HookContext
    ↓
  执行 Hook Pipeline (按优先级)
    ├→ Hook 1: FAQ (priority=10)
    ├→ Hook 2: 敏感词过滤 (priority=20)
    ├→ Hook 3: 输入验证 (priority=50)
    └→ ...
    ↓
  检查结果
    ├→ INTERCEPT → 直接返回，拦截后续流程
    ├→ MODIFY → 更新输入后继续
    ├→ SKIP → 跳过当前步骤
    └→ CONTINUE → 继续执行

  3. 内置 Hooks
  ┌─────────────────────────┬────────┬──────────────────────────┐
  │          Hook           │ 优先级 │           用途           │
  ├─────────────────────────┼────────┼──────────────────────────┤
  │ FAQHook                 │ 10     │ FAQ 拦截，命中则直接返回 │
  ├─────────────────────────┼────────┼──────────────────────────┤
  │ SensitiveWordHook       │ 20     │ 敏感词过滤               │
  ├─────────────────────────┼────────┼──────────────────────────┤
  │ PromptInjectionHook     │ 30     │ Prompt 注入检测          │
  ├─────────────────────────┼────────┼──────────────────────────┤
  │ InputValidatorHook      │ 50     │ 输入验证（长度、格式等） │
  ├─────────────────────────┼────────┼──────────────────────────┤
  │ RequestLoggerHook       │ 190    │ 请求日志记录             │
  ├─────────────────────────┼────────┼──────────────────────────┤
  │ StatisticsCollectorHook │ 195    │ 统计收集                 │
  └─────────────────────────┴────────┴──────────────────────────┘
  4. Agent 集成

  在 agent.py 中的关键修改：
  # 1. 初始化 Hooks
  def _init_hooks(self, config):
      # 注册内置 Hooks
      self.hook_manager.register(FAQHook())
      # ... 
      # 从配置加载自定义 Hooks
      hook_configs = HookConfigLoader.from_dict(config.get("hooks", {}))
      self.hook_manager.load_from_config(hook_configs)

  # 2. 在 run_task 中执行 Pipeline
  async def run_task(...):
      # 创建 HookContext
      hook_ctx = HookContext(user_input, state, gen, req_ctx)

      # 执行用户输入 Hooks
      hook_result = await self.hook_manager.on_user_input(hook_ctx)

      # 处理 Hook 结果
      if hook_result and hook_result.action == "intercept":
          # Hook 拦截了，直接返回
          return hook_result.response

  5. 配置文件示例

  在 assistant_config.yaml 中添加：
  # ================= Hooks 配置 =================
  hooks:
    # 自定义敏感词列表
    sensitive_word_filter:
      enabled: true
      priority: 20
      hook_type: "filter"
      params:
        words: ["暴力", "恐怖", "色情"]
        action: "intercept"  # intercept, replace, warn
        replacement: "***"

    # 自定义输入验证
    custom_input_validator:
      enabled: true
      priority: 45
      hook_type: "validator"
      params:
        max_length: 10000
        min_length: 1

    # 统计收集
    statistics_collector:
      enabled: true
      priority: 195
      hook_type: "observer"

  6. 数据流动管线

  用户输入 → HookContext → Hook Pipeline
                                   ↓
                           ┌────────────────────────┐
                           │  Hook 1 (FAQ)          │
                           │  - 检查 FAQ           │
                           │  - 命中 → INTERCEPT    │
                           └────────────────────────┘
                                   ↓ (未拦截)
                           ┌────────────────────────┐
                           │  Hook 2 (敏感词)       │
                           │  - 检测敏感词         │
                           │  - 发现 → INTERCEPT    │
                           └────────────────────────┘
                                   ↓ (未拦截)
                           ┌────────────────────────┐
                           │  Hook 3 (输入验证)     │
                           │  - 验证长度           │
                           │  - 无效 → INTERCEPT    │
                           └────────────────────────┘
                                   ↓ (通过)
                           继续正常的 Agent 流程

  7. 提前退出机制

  拦截场景:
  1. FAQ 命中 - 直接返回 FAQ 答案，不执行意图识别
  2. 敏感词检测 - 返回警告消息，拒绝处理
  3. 输入验证失败 - 返回错误提示，拒绝处理
  4. Prompt 注入检测 - 返回警告，拒绝处理

  修改场景:
  - 输入清洗（去除多余空格、特殊字符等）
  - 格式转换（繁简转换、大小写转换等）

  8. 使用示例

  创建自定义 Hook:
  from assistant.core.hooks import AgentHook, HookResult, HookContext, register_hook

  @register_hook("my_custom_hook")
  class MyCustomHook(AgentHook):
      name = "my_custom_hook"
      priority = 100  # 自定义优先级

      async def on_user_input(self, ctx: HookContext) -> Optional[HookResult]:
          # 自定义逻辑
          if "hello" in ctx.user_input.lower():
              return HookResult.intercept(
                  response="你好！有什么我可以帮助你的吗？"
              )
          return None

  注册到 Agent:
  # 在 Agent._init_hooks 中添加
  self.hook_manager.register(MyCustomHook())