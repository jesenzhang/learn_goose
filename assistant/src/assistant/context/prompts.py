REQUIREMENT_CLASSIFIER_PROMPT = (
    "你是一个文本分类器。给定多个分段文本，判断每段是“需求/指令”还是“背景资料”。"
    "仅输出 JSON，格式为："
    "{\"segments\":[{\"index\":0,\"label\":\"requirement|background\",\"confidence\":0.0}],\"notes\":\"\"}。"
    "confidence 取 0~1，表示该段属于 requirement 的置信度。"
)

REQUIREMENT_EXTRACTION_PROMPT = (
    "你是需求抽取器。请从输入文本中抽取真实需求并输出 JSON："
    "{\"goal\":\"\",\"scope\":\"\",\"constraints\":[],\"output_format\":\"\","
    "\"uncertainties\":[],\"need_clarification\":false,\"questions\":[]}。"
    "goal=目标；scope=输入资料范围；constraints=约束；output_format=预期输出格式；"
    "uncertainties=不确定点；need_clarification 表示是否需要澄清；questions 为澄清问题列表。"
    "只输出 JSON，不要多余文本。"
)

CONTEXT_SEGMENT_SUMMARY_PROMPT = (
    "你是一个助手，负责将用户的长文本分段压缩为可持续更新的摘要。"
    "必须输出以下结构（每项一行，中文）：\n"
    "目标：...\n"
    "约束：...\n"
    "关键事实：...\n"
    "未决问题：...\n"
    "要求：保留关键事实、实体、约束、用户目标；不要添加其他前缀。"
    "摘要控制在 500 字以内。"
)

DEFAULT_QUERY_REWRITE_PROMPT = (
    "You are a query rewriting assistant. Rewrite the user query to be explicit and "
    "self-contained using the provided conversation context and session memory. "
    "Keep it short and focused. Output ONLY the rewritten query text."
)
