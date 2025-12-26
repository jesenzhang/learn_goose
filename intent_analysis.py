from pydantic import BaseModel, Field,field_serializer, TypeAdapter,ValidationError
from typing import get_origin, get_args,Dict, List, Optional, Any,Union, Callable
import json
import time
import inspect
from abc import ABC, abstractmethod
import redis
import sqlite3
import asyncio

# 参数定义
class SlotSchema(BaseModel):
    name: str
    description: str
    required: bool = False
    
    # 允许传入 List[int], dict, type 等任何对象
    data_type: Any = str 

    options: Optional[List[str]] = None
    # [新增] 关键标志位：如果是 True，当此槽位值发生变化时，视为意图切换，清空旧上下文
    is_group_key: bool = False
    # 序列化器保持不变：为了给 LLM 生成 Prompt
    @field_serializer('data_type')
    def serialize_type(self, v: Any, _info):
        type_mapping = {int: "integer", str: "string", bool: "boolean", float: "number", list: "array"}
        
        # 处理原生类型
        if isinstance(v, type):
            return type_mapping.get(v, v.__name__)
        
        # 处理泛型 (借助 str() 简单处理，或者用之前的 get_origin 逻辑)
        # 例如 List[int] 转为字符串描述
        s_v = str(v)
        if "List" in s_v or "list" in s_v:
            if "int" in s_v: return "array of integers"
            if "str" in s_v: return "array of strings"
            return "array"
            
        return str(v)
    
# 意图定义
class IntentDefinition(BaseModel):
    name: str
    description: str
    slots: List[SlotSchema] = []

class IntentActionResult(BaseModel):
    """
    所有业务函数的统一返回结构
    """
    intent: str
    status: str = "ready" # success, failed, pending
    data: Any = None        # 核心业务数据 (Map 阶段产物)
    meta: Dict[str, Any] = {} # 元数据，如耗时、来源等

    # 标记是否需要立即结束对话，还是进入Reduce阶段
    needs_aggregation: bool = True
    
# --- 核心 Prompt 生成器 ---
class SlotFillingPromptBuilder:
    def __init__(self, intents: List[IntentDefinition]):
        self.intents = intents

    def _get_intents_json(self) -> str:
        """
        生成 Intent 列表的 JSON 描述。
        升级点：支持 List[int] 等泛型对象的自然语言描述生成。
        """
        export_data = []
        
        # 基础类型映射
        type_mapping = {
            int: "integer",
            float: "number",
            bool: "boolean",
            str: "string",
            list: "array",
            dict: "object"
        }

        for intent in self.intents:
            # 1. 序列化 (触发 SlotSchema 的 serializer)
            intent_dict = intent.model_dump()
            
            # 2. 二次加工 description
            processed_slots = []
            
            # 使用 zip 同时访问 原始定义(raw_slot) 和 序列化后的字典(slot_dict)
            for raw_slot, slot_dict in zip(intent.slots, intent_dict.get('slots', [])):
                
                constraints = []
                type_desc = None
                dt = raw_slot.data_type

                # --- 核心逻辑升级：解析类型 ---
                
                # 情况 A: 泛型 (例如 List[int])
                origin = get_origin(dt)
                if origin is list or origin is List:
                    args = get_args(dt)
                    inner_type = args[0] if args else Any
                    # 递归查一下内部类型的名字
                    inner_name = type_mapping.get(inner_type, "value")
                    type_desc = f"list of {inner_name}s" # 结果: "list of integers"

                # 情况 B: 原生类 (例如 int)
                elif isinstance(dt, type):
                    type_desc = type_mapping.get(dt, None)
                
                # 情况 C: 字符串 (例如 "integer")
                elif isinstance(dt, str):
                    type_desc = dt

                # --- 组装约束 ---
                if type_desc and type_desc != "string":
                    constraints.append(f"类型: {type_desc}")
                
                if raw_slot.options:
                    constraints.append(f"可选值: {raw_slot.options}")
                
                # --- 写入 Description ---
                if constraints:
                    # 最终生成的 Prompt 会像这样:
                    # "description": "设施ID (类型: list of integers)"
                    slot_dict['description'] += f" ({'; '.join(constraints)})"
                
                processed_slots.append(slot_dict)
            
            intent_dict['slots'] = processed_slots
            export_data.append(intent_dict)
            
        return json.dumps(export_data, ensure_ascii=False, indent=2)
    
    def _get_context_block(self, current_intent: Optional[str], history_entities: Dict[str, Any]) -> str:
        """构建动态上下文板块"""
        if not current_intent:
            return "- Current Intent: None (New Conversation)\n- Known Entities: {}"
        
        entities_json = json.dumps(history_entities, ensure_ascii=False)
        return f"- Current Intent: {current_intent}\n- Known Entities: {entities_json}"

    def build(self, user_query: str, current_intent: str = None, history_entities: dict = None, background_info: str = "") -> str:
        """
        组装最终 Prompt。
        """
        if history_entities is None:
            history_entities = {}

        # 1. 准备动态数据
        intents_str = self._get_intents_json()
        context_str = self._get_context_block(current_intent, history_entities)
        
        # 2. 定义 Prompt 模板
        
        part_role = """
# Role
你是一个智能意图识别与槽位填(slot filling)充专家。

# 你的目标是：准确识别用户意图，从对话中提取参数，并输出标准 JSON。

"""

        part_constraints = """
# Instructions (Think Step-by-Step)
请按照以下步骤思考（在输出的 "_thought" 字段中体现）：
1. **意图分析**：分析用户属于 Intent List 中的哪一个意图。
2. **信息检索**：
- 检查 "Current Context" 中已有的参数。
- 从 "User Input" 中提取新的参数。
- **合并策略**：如果用户提供了新值，覆盖旧值；否则保留 Context 中的旧值。
3. **高级推理**（仅针对特定情况）：
- 如果是 `recommend` 且用户描述模糊（如“能响的”），请查阅 "Background Information" 找到对应的 ID。
- 如果参数缺失但能通过 "Background Information" 唯一确定（如已知名字查ID），则自动补全。
4. **状态检查**：检查该意图所需的必填参数是否齐全。
- 齐全 -> status: "ready"
- 缺失 -> status: "incomplete" -> 生成 reply_to_user 追问。
5. **格式化**：将提取的数字转换为 integer/float，去除单位（如 "5个" -> 5）。


 Constraints
1. 只能从提供的意图列表中选择。
2. 输出必须是严格的 JSON 格式。
3. **状态判断**：
   - 如果必填参数缺失，status 设为 "incomplete"，并生成 reply_to_user 进行追问。
   - 如果所有必填参数都在 entities 中，status 设为 "ready"。
4. **合并逻辑**：不要忽略 Context 中的信息，除非用户明确修改了它。
5. 始终用中文回答。
6. **类型转换**：请根据 intent 定义中的类型提示（如 integer, boolean）转换提取的值。例如不要返回 "5个"，而是返回 5。
7. 如果参数缺失，但可以通过 Background Information 推断出来（例如通过名称查到ID），则视为参数已就绪 (status: ready)，并自动填充推断出的值。
8. 提取用户感兴趣的特征形容词作为 tags
9. **推荐逻辑**：当意图是 `recommend` 时，请仔细阅读 # Background Information。利用你的常识理解用户的模糊描述（例如用户说“能响的东西” -> 对应“军号”；“由于细菌引起的” -> 对应“细菌弹”），找出所有语义相关的项，提取其 ID 填入 `recommended_ids`。


# Search & Quantity Policy

1. **相关性绝对优先 (Relevance > Quantity)**：
   - 必须先根据语义筛选出真正匹配的项目。
   - **严禁凑数**：如果用户要求 N 个（如“两把枪”），但只有 M 个符合描述（M < N），**只返回这 M 个**。如果没有任何符合的项目，`recommended_ids` 必须返回空列表 `[]`。
   - 不要为了满足数量 N 而塞入不相关的项目。

2. **数量不足时的反馈逻辑**：
   - 如果 `找到的数量 < 用户要求的数量`，必须在 **`reply_to_user`** 字段中向用户解释。
   - 话术模版：“为您找到了 [M] 个相关文物（虽然您想看 [N] 个，但目前符合条件的只有这些）...”
   
"""

        part_examples = ''
        
        part_data = f"""
# Background Information
{background_info}

# Intent List (定义与规则)
{intents_str}

# Current Context (多轮对话上下文)
{context_str}

# User Input
{user_query}
"""

        part_format = """
# Output Format
请仅返回如下 JSON 格式，不要包含 Markdown 代码块标记：
{
    "_thought": "思考过程",
    "intent": "意图名称",
    "confidence": 0.95,
    "status": "ready/incomplete", 
    "entities": {
        "key": "value (合并后的最终结果)"
    },
    "missing_slots": ["缺失参数1", "缺失参数2"],
    "reply_to_user": "追问话术 或 确认话术"
}
"""


        # part_role = """
        # # Role
        # 你是一个专业的意图识别与参数提取助手。
        # 你的目标是：准确识别用户意图，从对话中提取参数，并输出标准 JSON。
        # """

        # part_constraints = """
        # # Instructions (Think Step-by-Step)
        # 请按照以下步骤思考（在输出的 "_thought" 字段中体现）：
        # 1. **意图分析**：分析用户属于 Intent List 中的哪一个意图。
        # 2. **信息检索**：
        # - 检查 "Current Context" 中已有的参数。
        # - 从 "User Input" 中提取新的参数。
        # - **合并策略**：如果用户提供了新值，覆盖旧值；否则保留 Context 中的旧值。
        # 3. **高级推理**（仅针对特定情况）：
        # - 如果是 `recommend` 且用户描述模糊（如“能响的”），请查阅 "Background Information" 找到对应的 ID。
        # - 如果参数缺失但能通过 "Background Information" 唯一确定（如已知名字查ID），则自动补全。
        # 4. **状态检查**：检查该意图所需的必填参数是否齐全。
        # - 齐全 -> status: "ready"
        # - 缺失 -> status: "incomplete" -> 生成 reply_to_user 追问。
        # 5. **格式化**：将提取的数字转换为 integer/float，去除单位（如 "5个" -> 5）。

        # # Constraints
        # 1. 必须输出且仅输出 JSON 格式，不要使用 Markdown 代码块。
        # 2. JSON 必须包含 `_thought` 字段，用于展示你的思考过程（这有助于提高准确率）。
        # 3. 始终使用中文回复用户。
        # """

        # part_examples = """
        # # Examples (参考样例)

        # ## Example 1 (参数提取与合并)
        # Context: {"city": "北京"}
        # User Input: "帮我订明天的票"
        # Intent Definition: book_ticket (slots: city, date)
        # Output:
        # {
        #     "_thought": "用户想订票。Context已有city=北京。用户输入提及'明天'，转换为日期。city和date都齐了。",
        #     "intent": "book_ticket",
        #     "confidence": 0.98,
        #     "status": "ready",
        #     "entities": {
        #         "city": "北京",
        #         "date": "2025-12-26"
        #     },
        #     "missing_slots": [],
        #     "reply_to_user": "好的，这就为您预订明天北京的票。"
        # }

        # ## Example 2 (模糊推荐与背景知识推理)
        # Background Info: {"item_101": {"name": "军号", "desc": "可以吹响的声音洪亮的乐器"}}
        # Context: {}
        # User Input: "我想看那个能吹响的东西"
        # Intent Definition: recommend (slots: recommended_ids)
        # Output:
        # {
        #     "_thought": "用户意图是推荐物品。描述是'能吹响'。查阅背景信息，'军号(item_101)'符合描述。提取ID。",
        #     "intent": "recommend",
        #     "confidence": 0.95,
        #     "status": "ready",
        #     "entities": {
        #         "recommended_ids": ["item_101"]
        #     },
        #     "missing_slots": [],
        #     "reply_to_user": "您是指军号吗？它确实可以发出嘹亮的声音。"
        # }

        # ## Example 3 (缺失参数追问)
        # Context: {}
        # User Input: "我要买票"
        # Intent Definition: buy_ticket (slots: count, type)
        # Output:
        # {
        #     "_thought": "用户想买票，但未提供数量和类型。参数缺失。",
        #     "intent": "buy_ticket",
        #     "confidence": 0.90,
        #     "status": "incomplete",
        #     "entities": {},
        #     "missing_slots": ["count", "type"],
        #     "reply_to_user": "好的，请问您需要购买哪种类型的票？需要几张？"
        # }
        # """

        # part_data = f"""
        # # Background Information
        # {background_info}

        # # Intent List (定义)
        # {intents_str}

        # # Current Context
        # {context_str}

        # # User Input
        # {user_query}
        # """

        # part_format = """
        # # Output Requirement
        # 请基于以上逻辑和样例，处理 User Input。
        # """

        final_prompt = f"{part_role}\n{part_constraints}\n{part_examples}\n{part_data}\n{part_format}"
        return final_prompt.strip()


# --- 数据模型 (DTO) ---
class DialogueSession(BaseModel):
    """
    管理单个用户的会话状态
    """
    session_id: str
    current_intent: Optional[str] = None       # 当前正在进行的意图
    collected_slots: Dict[str, Any] = {}       # 已收集的参数 {key: value}
    # 可选：如果你希望 LLM 能理解"改为明天"，保留最近几轮原始对话很有用
    chat_history: List[Dict[str, str]] = []    
    last_updated: float = 0.0
    
     # 辅助方法：判断是否超时（可选）
    def is_expired(self, ttl_seconds: int = 1800) -> bool:
        return time.time() - self.last_updated > ttl_seconds
    
    def update_slots(self, new_slots: Dict[str, Any]):
        """合并新提取的槽位到已有槽位中"""
        if new_slots:
            self.collected_slots.update(new_slots)
    
    def clear_intent(self):
        """意图完成或取消时重置"""
        self.current_intent = None
        self.collected_slots = {}
        



class SessionStorage(ABC):
    @abstractmethod
    def load(self, session_id: str) -> Optional[DialogueSession]:
        pass

    @abstractmethod
    def save(self, state: DialogueSession):
        pass

# --- Redis 实现 ---
class RedisSessionStorage(SessionStorage):
    def __init__(self, redis_url: str = "redis://:KmSHIVajOm@192.168.10.198:6379/0",prefix:str="dialogue_session:", ttl: int = 3600):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.ttl = ttl  # 会话过期时间（秒）
        self.prefix = prefix

    def load(self, session_id: str) -> Optional[DialogueSession]:
        data = self.redis.get(f"{self.prefix}{session_id}")
        if data:
            return DialogueSession.model_validate_json(data)
        return None

    def save(self, state: DialogueSession):
        state.last_updated = time.time()
        # 将 Pydantic 对象转为 JSON 字符串存储
        res = self.redis.setex(
            f"{self.prefix}{state.session_id}", 
            self.ttl,
            state.model_dump_json()
        )
        print(res)

class SQLiteSessionStorage(SessionStorage):
    def __init__(self, db_path="sessions.db", ttl=3600):
        self.db_path = db_path
        self.ttl = ttl
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data TEXT,
                    updated_at REAL
                )
            """)

    def load(self, session_id: str) -> Optional[DialogueSession]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data, updated_at FROM sessions WHERE session_id = ?", 
                (session_id,)
            )
            row = cursor.fetchone()
            
            if row:
                data_str, updated_at = row
                # 检查过期
                if time.time() - updated_at > self.ttl:
                    return None # 已过期
                return DialogueSession.model_validate_json(data_str)
            return None

    def save(self, state: DialogueSession):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (session_id, data, updated_at)
                VALUES (?, ?, ?)
            """, (state.session_id, state.model_dump_json(), time.time()))
            
class MemorySessionStorage(SessionStorage):
    def __init__(self):
        self._store = {}

    def load(self, session_id):
        return self._store.get(session_id)

    def save(self, state):
        self._store[state.session_id] = state
        
class DialogueManager:
    def __init__(self, agent: 'IntentAgent', storage: SessionStorage):
        self.agent = agent
        self.storage = storage

    async def handle_request(self, session_id: str, user_input: str,background_info:str='') -> List[Dict[str, Any]]:
        # 1. LOAD: 尝试从存储中恢复状态
        state = self.storage.load(session_id)
        
        # 如果是新用户或会话已过期，创建一个新的空状态
        if not state:
            state = DialogueSession(session_id=session_id)
            print(f"[Log] Created new session for {session_id}")

        # 2. 转换状态: 将持久化状态转为 Agent 需要的 Session 对象
        # (因为你的 Agent 逻辑是用 DialogueSession 类操作的，这里做一个简单的映射)
        # 这里的 session 对象只是临时的，仅存在于这次函数调用栈中
        temp_session = DialogueSession(
            session_id=state.session_id,
            current_intent=state.current_intent,
            collected_slots=state.collected_slots
        )

        # 3. PROCESS: 调用核心智能体逻辑
        ## LLM 返回结构预期: {"intents": [ {...}, {...} ]}
        result = await self.agent.chat(user_input,background_info=background_info,session=temp_session)
        # 兼容性处理：如果 LLM 还是返回了老格式（单个字典），强转为列表
        if "intents" in result:
            raw_intents = result["intents"]
        else:
            # 兼容旧格式兜底
            raw_intents = [result]
            
        print(result)
        
        processed_results = []
        primary_incomplete_intent = None # 用于记录主要焦点的未完成意图
        
        # 3. 遍历处理每个意图
        for item in raw_intents:
            intent_name = item.get("intent")
            
            # 这里的 entities 是 LLM 提取的本轮增量
            extracted_entities = item.get("entities", {})

            # 3.1 状态管理逻辑 (简化版)
            # 如果是当前正在聊的意图，合并历史槽位
            # 如果是新意图，从零开始
            # 注意：在多意图并发下，槽位合并比较复杂。这里采用简单策略：
            # 只有当 intent_name 等于 session 中记录的 current_intent 时，才合并历史。
            
            current_slots = {}
            if intent_name == temp_session.current_intent:
                current_slots = temp_session.collected_slots.copy()
            
            # 合并本轮新提取的
            current_slots.update(extracted_entities)

            # 3.2 Python 侧二次校验 (复用 Agent 的逻辑)
            # 先做类型转换
            current_slots = self.agent._post_process_slots(intent_name, current_slots)
            # 再做完整性校验
            real_status, missing = self.agent._validate_completeness(intent_name, current_slots)

            # 3.3 构建单个结果
            processed_item = {
                "intent": intent_name,
                "status": real_status,
                "entities": current_slots, # 这是合并后的完整参数
                "missing_slots": missing,
                "reply_to_user": item.get("reply_to_user")
            }

            # 如果状态不完整，且还没有确定的主意图，则生成追问
            if real_status == "incomplete":
                if not processed_item["reply_to_user"]:
                    processed_item["reply_to_user"] = f"请提供 {missing[0]} 信息。"
                
                # 锁定第一个未完成的意图作为 Session 的主要状态
                if primary_incomplete_intent is None:
                    primary_incomplete_intent = {
                        "intent": intent_name,
                        "slots": current_slots
                    }
            
            processed_results.append(processed_item)
        
        # 4. 更新 Session State (SAVE)
        # 策略：如果存在未完成意图，Session 停留在该意图；
        # 如果所有意图都 Ready 了，清空 Session (视为一次性任务全部完成)
        if primary_incomplete_intent:
            state.current_intent = primary_incomplete_intent["intent"]
            state.collected_slots = primary_incomplete_intent["slots"]
        else:
            # 全部 Ready 或 闲聊，清空上下文
            state.clear_intent()

        self.storage.save(state)

        return processed_results

class IntentAgent:
    def __init__(self, client, intents: List[IntentDefinition]):
        self.client = client
        self.intents = intents
        # 建立意图查找表，方便后续根据名字找定义
        self.intent_map = {i.name: i for i in intents}
        # 复用你写的 PromptBuilder
        self.prompt_builder = SlotFillingPromptBuilder(intents)

    async def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """封装 LLM 调用与 JSON 解析"""
        try:
            reasoning_text=''
            content_text=''
            tool_calls=[]
            async for chunk in self.client.astream(input=[{"role":"user","content":prompt}]):
                reasoning,content,tool = chunk
                reasoning_text+=reasoning
                content_text+=content
                if tool:
                    tool_calls.append(tool)
            return json.loads(content_text)
        except Exception as e:
            # 生产环境建议记录日志
            print(f"LLM Call Error: {e}")
            return {"status": "error", "reply_to_user": "系统繁忙，请稍后再试。"}

    def _validate_completeness(self, intent_name: str, slots: Dict[str, Any]) -> tuple[str, List[str]]:
        """
        [Python侧兜底校验 - 增强版]
        检查必填参数是否真的齐了，并排除空值（空列表、空字符串、None）。
        """
        intent_def = self.intent_map.get(intent_name)
        if not intent_def:
            return "unknown", []
        missing = []
        for slot in intent_def.slots:
            # 只检查必填项
            if not slot.required:
                continue
            val = slots.get(slot.name)
            # --- 校验规则 1: 绝对空值 ---
            if val is None:
                missing.append(slot.name)
                continue
            # --- 校验规则 2: 容器类型的空值检查 ---
            # 针对 List, Dict, Tuple, Set, String
            if isinstance(val, (list, dict, str, tuple, set)):
                if len(val) == 0:
                    missing.append(slot.name)
                    continue
                # 特殊处理: 字符串如果是纯空格，也算缺失
                if isinstance(val, str) and not val.strip():
                    missing.append(slot.name)
                    continue

            # --- 校验规则 3 (可选): 自定义规则 ---
            # 如果你是 List 类型，但业务要求至少选 2 个，可以在这里加 len(val) < 2 的判断
            
            # 注意：这里故意没有使用 `if not val:` 
            # 因为我们允许 val 为 0 (int) 或 False (bool)

        status = "incomplete" if missing else "ready"
        return status, missing
    
    def _post_process_slots(self, intent_name: str, slots: Dict[str, Any]) -> Dict[str, Any]:
        intent_def = self.intent_map.get(intent_name)
        if not intent_def:
            return slots

        cleaned_slots = slots.copy()

        for slot in intent_def.slots:
            val = cleaned_slots.get(slot.name)
            if val is None:
                continue

            try:
                # 1. 创建 TypeAdapter
                # Pydantic 会自动理解 List[int], int, bool 等类型
                adapter = TypeAdapter(slot.data_type)

                # 2. [关键] 处理 LLM 返回的字符串形式的列表
                # LLM 经常返回 "['1', '2']" (字符串) 而不是 ['1', '2'] (列表)
                # Pydantic 默认不会自动把 JSON 字符串转列表，需要我们帮一下忙
                if isinstance(val, str) and (str(slot.data_type).startswith("typing.List") or str(slot.data_type).startswith("list")):
                     if val.strip().startswith("["):
                         try:
                             val = json.loads(val)
                         except:
                             pass # 解析失败就硬传给 validator 试试
                     elif "," in val:
                         # 处理 "1, 2, 3" 这种情况
                         val = val.split(",")

                # 3. [核心] 验证并转换 (Validate Python)
                # 这行代码会自动做以下事情：
                # - 如果 data_type 是 int，它会把 "5" 转为 5
                # - 如果 data_type 是 List[int]，它会把 ["1", "2"] 转为 [1, 2]
                # - 如果 data_type 是 bool，它会把 "true" 转为 True
                converted_val = adapter.validate_python(val)
                
                cleaned_slots[slot.name] = converted_val

            except (ValidationError, ValueError) as e:
                # 验证失败，说明 LLM 提取的内容不符合类型要求
                print(f"[Warn] 类型校验失败: Slot '{slot.name}' 期望 {slot.data_type}, 实际值 '{val}'")
                del cleaned_slots[slot.name]
                continue

            # 4. 枚举校验 (Options Check) - 保持不变
            if slot.options:
                # 注意：对于 List 类型，通常不校验 options，或者需要校验 list 中的每个元素
                # 这里假设 options 仅针对单值类型，或者你需要实现更复杂的逻辑
                if not isinstance(converted_val, list) and converted_val not in slot.options:
                     del cleaned_slots[slot.name]

        return cleaned_slots
    
    async def chat(self, user_input: str,background_info:str, session: DialogueSession) -> Dict[str, Any]:
        """
        核心交互方法
        """
        prompt = self.prompt_builder.build(
            user_query=user_input,
            current_intent=session.current_intent,
            history_entities=session.collected_slots,
            background_info=background_info
        )

        # 2. 调用 LLM
        result = await self._call_llm(prompt)
        print("新意图结果:" + str(result))
        # 3. 错误处理
        if result.get("status") == "error":
            return result

        # 4. 状态更新逻辑 (State Management)
        new_intent = result.get("intent")
        new_entities = result.get("entities", {})

        should_clear_session = False
        
        # 判定 1: 显式意图切换 (Intent Name 变了)
        if session.current_intent and new_intent != session.current_intent:
            print(f"[System] 显式意图切换: {session.current_intent} -> {new_intent}")
            should_clear_session = True
        
        # 判定 2: 隐式子意图切换 (Intent 不变，但 Group Key 变了)
        elif session.current_intent and new_intent == session.current_intent:
            intent_def = self.intent_map.get(new_intent)
            if intent_def:
                for slot in intent_def.slots:
                    # 只检查被标记为“关键槽位”的字段
                    if getattr(slot, 'is_group_key', False):
                        new_val = new_entities.get(slot.name)
                        old_val = session.collected_slots.get(slot.name)
                        
                        # 逻辑：如果新提取到了值，且跟老值不一样 -> 视为切换
                        # 注意：如果 new_val 为空，说明用户没提类别，默认继承上下文，不算切换
                        if new_val is not None and old_val is not None and new_val != old_val:
                            print(f"[System] 子类别切换 ({slot.name}): {old_val} -> {new_val}")
                            should_clear_session = True
                            break
                        
        # 执行清除
        if should_clear_session:
            session.clear_intent()                
        
        if not session.current_intent:
            session.current_intent = new_intent
        
        # 更新 Session
        session.current_intent = new_intent
        session.update_slots(new_entities)

        # 5. [关键] Python侧二次校验
        # LLM 可能会幻觉说 status: ready，但其实缺参数，我们需要纠正它
        if session.current_intent:
            session.collected_slots = self._post_process_slots(session.current_intent, session.collected_slots)
            
            real_status, missing_slots = self._validate_completeness(
                session.current_intent, 
                session.collected_slots
            )
            
            # 覆写结果
            result["status"] = real_status
            result["missing_slots"] = missing_slots
            result["final_slots"] = session.collected_slots # 返回合并后的完整参数
            
            # 如果 Python 发现缺参数，但 LLM 以为齐了没生成追问，我们需要强制生成追问（或在前端处理）
            # 这里简单处理：如果状态是不完整，但 LLM 没给追问，人工补一个（可选）
            if real_status == "incomplete" and not result.get("reply_to_user"):
                 result["reply_to_user"] = f"请提供 {missing_slots[0]} 信息。"

        return result

class IntentRouter:
    def __init__(self, client, storage: SessionStorage):
        self.client = client
        self.storage = storage
        
        # 注册表
        self.intents_list: List[IntentDefinition] = []
        self.handlers: Dict[str, Callable] = {}
        
        # 懒加载 Manager (因为需要等所有意图注册完才能初始化 Agent)
        self._manager: Optional[DialogueManager] = None

    def add_handler(self, intent_def: IntentDefinition, handler_func: Callable):
        """
        手动注册处理函数（供类内部扫描使用）
        """
        # print(f"[Router] Registering: {intent_def.name} -> {handler_func.__name__}")
        self.intents_list.append(intent_def)
        self.handlers[intent_def.name] = handler_func

    def register(self, intent_def: IntentDefinition):
        """装饰器写法 (保持兼容)"""
        def decorator(func):
            self.add_handler(intent_def, func)
            return func
        return decorator

    @property
    def manager(self) -> DialogueManager:
        """
        初始化并返回会话管理器 (Singleton模式)
        """
        if self._manager is None:
            # 1. 创建 Agent
            agent = IntentAgent(self.client, self.intents_list)
            # 2. 创建 Manager (包裹 Agent 和 Storage)
            self._manager = DialogueManager(agent, self.storage)
        return self._manager

    async def handle_message_single(self, session_id: str, message: str, **context_kwargs) -> str:
        """
        [统一入口] 处理用户消息
        """
        # --- STEP 1: 多轮对话与槽位填充 (State Management) ---
        # 这一步负责：Load Redis -> LLM Analyze -> Merge Slots -> Check Required -> Save Redis
        try:
            process_result = await self.manager.handle_request(session_id, message, **context_kwargs)
        except Exception as e:
            return f"系统处理请求时发生错误: {str(e)}"
        
        status = process_result.get("status")
        
        
        # --- STEP 2: 决策分发 (Decision & Routing) ---
        
        # 情况 A: 参数不全 (Incomplete) 或 闲聊 (General Chat)
        # 动作: 直接返回 LLM 生成的追问话术，不执行业务逻辑
        if status != "ready":
            # 返回一个特殊的 Result，告诉外层直接显示 reply_to_user
            return IntentActionResult(
                intent=process_result.get("intent", "unknown"),
                status="incomplete",
                data=process_result.get("reply_to_user"),
                needs_aggregation=False 
            )
            # return status,intent_name,process_result.get("reply_to_user") or "抱歉，我没理解您的意思。"
        
        
        # 情况 B: 参数齐备 (Ready)
        # 动作: 路由到对应的 Python 函数执行业务
        intent_name = process_result.get("intent")
        handler = self.handlers.get(intent_name)
        if not handler:
            return f"[System Error] 意图 '{intent_name}' 没有注册处理函数。"

        # --- STEP 3: 动态参数注入 (Dependency Injection) ---
        # 准备参数：LLM 提取的实体 + 外部注入的上下文(如 db, user_id)
        extracted_slots = process_result.get("entities", {}) or {} # 确保是字典
        
        # 合并参数 (slots 覆盖 context，或者反过来，视需求而定)
        # 建议: context 优先，防止用户伪造 user_id
        execution_kwargs = {**extracted_slots, **context_kwargs}

        try:
            # 过滤参数：只传函数需要的参数，防止报错
            sig = inspect.signature(handler)
            valid_keys = [p.name for p in sig.parameters.values() 
                          if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
            
            final_kwargs = {k: v for k, v in execution_kwargs.items() if k in valid_keys}
            
            print(f"   >>> [Router] Executing {intent_name} with {final_kwargs}")
            
            async_func = inspect.iscoroutinefunction(handler)
            if async_func:
                # 异步函数调用
                business_response = await handler(**final_kwargs)
            else:
                # 同步函数调用
                business_response = handler(**final_kwargs)
            
            # (可选) 执行成功后，是否要清空当前 Session 的意图？
            # self.manager.clear_session(session_id) 
            # 归一化：确保返回的是 ActionResult
            if isinstance(business_response, IntentActionResult):
                return business_response
            else:
                # 兼容旧代码，如果返回字符串或字典，自动包装
                return IntentActionResult(intent=intent_name, data=business_response)
            # return status,intent_name,business_response

        except Exception as e:
            # 生产环境建议记录详细日志
            return 'error','error',f"系统处理业务时发生错误: {str(e)}"
    
    
    async def handle_message(self, session_id: str, message: str, **context_kwargs) -> IntentActionResult:
        """
        [修改] 支持并发执行并聚合结果，返回单一的 IntentActionResult 用于前端展示
        """
        try:
            # 1. 获取处理结果列表 (List[Dict])
            processed_results = await self.manager.handle_request(session_id, message, **context_kwargs)
        except Exception as e:
            return IntentActionResult(intent="error", status="failed", data=f"Intent Analysis Error: {str(e)}")

        tasks = []
        fallback_responses = [] # 用于收集不需要执行业务逻辑的回复（如追问、闲聊）

        # 2. 任务分发
        for res in processed_results:
            intent_name = res["intent"]
            status = res["status"]
            slots = res["entities"]
            reply = res.get("reply_to_user")

            # 情况 A: 闲聊 或 参数缺失 -> 不执行 Handler，直接收集回复
            if intent_name == "general_chat" or status != "ready":
                fallback_responses.append(reply or "我还在学习中...")
                continue

            # 情况 B: 准备就绪 -> 寻找 Handler 并准备并发
            handler = self.handlers.get(intent_name)
            if handler:
                # 注入参数
                sig = inspect.signature(handler)
                valid_keys = [p.name for p in sig.parameters.values() 
                              if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
                
                # 合并 slots 和外部 context
                execution_kwargs = {**slots, **context_kwargs}
                final_kwargs = {k: v for k, v in execution_kwargs.items() if k in valid_keys}

                print(f"   >>> [Router] Concurrency Task Add: {intent_name} with {final_kwargs}")

                # 包装 Task
                if inspect.iscoroutinefunction(handler):
                    tasks.append(asyncio.create_task(handler(**final_kwargs)))
                else:
                    tasks.append(asyncio.to_thread(handler, **final_kwargs))
            else:
                fallback_responses.append(f"未找到意图 {intent_name} 的处理能力")

        # 3. 并发执行
        business_results = []
        if tasks:
            # return_exceptions=True 防止一个炸了全部炸
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in raw_results:
                if isinstance(r, Exception):
                    business_results.append(IntentActionResult(intent="error", status="failed", data=str(r)))
                elif isinstance(r, IntentActionResult):
                    business_results.append(r)
                else:
                    # 兼容普通返回值
                    business_results.append(IntentActionResult(intent="unknown", data=r))

        # 4. 结果聚合 (Aggregation)
        final_response = self._aggregate_responses(business_results, fallback_responses)
        
        return final_response

    def _aggregate_responses(self, business_results: List[IntentActionResult], fallback_texts: List[str]) -> IntentActionResult:
        """
        将业务执行结果和闲聊/追问文本合并
        """
        final_text_parts = []
        combined_meta = {}
        combined_data_list = [] # 如果你需要返回结构化数据列表

        # 1. 处理业务成功结果
        for res in business_results:
            if res.status == "failed":
                final_text_parts.append(f"❌ {res.data}")
            else:
                # 这里假设 res.data 是字符串，或者是可以转字符串的对象
                # 如果你的 Handler 返回的是复杂对象，这里需要定制化 formatting
                if isinstance(res.data, str):
                    final_text_parts.append(f"✅ {res.data}")
                else:
                    final_text_parts.append(f"✅ 已处理: {res.intent}")
                
                # 收集 meta 信息 (比如推荐列表)
                if res.meta:
                    combined_meta.update(res.meta)
                combined_data_list.append(res.data)

        # 2. 处理追问/闲聊
        for text in fallback_texts:
            # 去重
            if text and text not in final_text_parts:
                final_text_parts.append(text)

        # 3. 组装最终文本
        if not final_text_parts:
            full_text = "抱歉，我没有理解您的请求。"
        else:
            full_text = "\n\n".join(final_text_parts)

        # 返回聚合后的结果
        # 注意：这里我们返回一个聚合的 IntentActionResult
        # intent 标记为 'multi_intent_aggregated'
        return IntentActionResult(
            intent="multi_intent_aggregated",
            status="success",
            data=full_text, 
            meta={
                "raw_data_list": combined_data_list, # 保留原始数据供前端使用
                **combined_meta
            }
        )
     
    
# 定义推荐意图
recommend_intent = IntentDefinition(
    name="recommend_items",
    description="用户希望推荐展品、设施或路线。通常包含形容词（如'好看的'、'红色的'、'打仗用的'）或模糊描述。",
    slots=[
        SlotSchema(
            name="category",
            description="用户想推荐的类别，例如 'exhibit'(展品),'exhibition'(展览), 'service'(设施/卫生间), 'route'(路线)。如果不确定，默认为 'exhibit'。",
            required=True,
            data_type=str,
            options=["exhibit","exhibition", "service", "route"]
        ),
        SlotSchema(
            name="recommended_ids",
            # 核心修改：描述中强制要求 LLM 根据语义去匹配 ID
            description="根据用户的描述（如'红色的'、'适合小孩的'），运用你的常识，在 Background Information 中寻找所有符合该描述的项目，并返回它们的 ID 列表。",
            required=True, # 这里设为 True，因为如果推荐不出 ID，这个意图就没意义了
            data_type=List[int] 
        ),
        SlotSchema(
            name="floor",
            description="楼层限制",
            required=False,
            data_type=int
        ),
    ]
)

# 2. 定义意图
defined_intents = [
    IntentDefinition(
        name="query_service_info",
        description="查询服务设施。",
        slots=[
            SlotSchema(name='keywords',description="用户想要找的设施的名称，如'电梯', '卫生间'",required=True,data_type=str),
            SlotSchema(name='floor',description='楼层',required=True,data_type=int),
            SlotSchema(name='id',description='设施ID,用于查询设施信息,如果用户提到设施名称，从背景信息中查找对应的ID填入',required=False,data_type=List[int]),
        ]
    ),
    IntentDefinition(
        name="query_exhibit_info",
        description="查询展品。",
        slots=[
            SlotSchema(name='keywords',description="用户想要找的展品的关键词，如'金星奖章', '瓷器'",required=True,data_type=str),
            SlotSchema(name='id',description='展品ID,用于查询展品信息,如果用户提到的展品可以从背景信息中查找到，则将对应的ID填入，如果用户要求推荐，则随机选取相关的展品的ID填入',required=False,data_type=List[int]),
        ]
    ),
    IntentDefinition(
        name="query_exhibition_info",
        description="查询展览",
        slots=[
            SlotSchema(name='keywords',description="用户想要找的展览的关键词，如'人民军队兵器陈列'",required=True,data_type=str),
            SlotSchema(name='exhibition_id',description='展览ID,用于查询展览信息,如果用户提到的展览可以从背景信息中查找到，则将对应的ID填入，如果用户要求推荐，则随机选取相关的展览的ID填入',required=False,data_type=List[int]),
        ]
    ),
    IntentDefinition(
        name="query_route_info",
        description="查询推荐浏览路线",
        slots=[
            SlotSchema(name='keywords',description="用户想要找的推荐浏览路线的关键词，如'亲子路线'",required=True,data_type=str),
            SlotSchema(name='indoor',description='是否在馆内',required=True,data_type=bool),
            SlotSchema(name='id',description='路线ID,用于查询路线信息,如果用户提到的路线可以从背景信息中查找到，则将对应的ID填入，如果用户要求推荐，则随机选取相关的路线的ID填入',required=False,data_type=List[int]),
        ]
    ),
    recommend_intent,
    
    IntentDefinition(
        name="general_chat",
        description="用户只是在闲聊，或者是打招呼，没有特定的业务请求。",
        slots=[
            SlotSchema(name='question',description='充分理解分析后的的询问问题',required=True,data_type=str),
            SlotSchema(name='keywords',description="提取出的关键词，如'人民军队兵器陈列'",required=True,data_type=List[str]),
            SlotSchema(name='raw_input',description='用户原始输入',required=True,data_type=str),
        ]
    )
]

from langchain.chat_models import init_chat_model

def create_intent_router():
    """
    创建意图代理实例
    """
    llm = init_chat_model(model = 'qwen3_vl',model_provider='openai',base_url = 'http://192.168.10.180:8088/v1/',api_key='vllm')
    storage=MemorySessionStorage()
    bot = IntentRouter(llm, storage)
    return bot

router = create_intent_router()
@router.register(IntentDefinition(
        name="book_ticket",
        description="预定机票",
        slots=[
            SlotSchema(name='date',description="日期",required=True,data_type=str),
            SlotSchema(name='dest',description="目的地",required=True,data_type=str),
            SlotSchema(name='count',description="数量",required=True,data_type=int),
        ]          
    ))
async def handle_ticket(date: str,dest:str, count: int):
    await asyncio.sleep(1) # 模拟耗时
    return f"已预订{date}的{count}张票"

@router.register(IntentDefinition(
    name="query_weather", 
    description="查询天气",
    slots=[
        SlotSchema(name='date',description="日期",required=True,data_type=str),
        SlotSchema(name='city',description="目标城市",required=True,data_type=str),
    ]   ))
async def handle_weather(city: str,date:str):
    await asyncio.sleep(1) # 模拟耗时
    return f"{city}天气晴朗"
    
    
async def test():
    print("----- 开始对话 (输入 q 退出) -----")
    while True:
        user_input = input("\nUser: ")
        if user_input.lower() == 'q':
            break
        
        intent_result = await router.handle_message(session_id="user_123", message=user_input, background_info="当前时间: 2024年5月20日 星期一")
        
        # 打印结果
        print(intent_result)
        
        # # 调试信息：查看内部状态变化
        # print(f"   [Debug Status]: {response.get('status')}")
        # print(f"   [Debug Slots] : {user_session.collected_slots}")
        
        # # 如果意图已就绪，可以在这里触发业务函数
        # if response.get("status") == "ready":
        #     print(f"   >>> 触发业务逻辑: 正在为用户预订去 {user_session.collected_slots['destination']} 的票...")
        #     # 业务执行完后，可以选择清空会话
        #     user_session.clear_intent()
 
if __name__ == "__main__":
  
    asyncio.run(test())
