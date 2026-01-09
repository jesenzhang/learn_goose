import os
import frontmatter
import importlib.util
import inspect
import sys
import re
from typing import Dict, List, Any, Optional
from ai_services import BaseAIService

class AnthropicSkillLoader:
    def __init__(self, skills_dir="agent_skills",ai_services: BaseAIService = None, sensitive_tools:List[str]=None, enabled_skills:List[str]=None,disabled_skills:List[str] = None):
        self.skills_dir = skills_dir
        self.ai_services = ai_services # 持有单例服务
        self.enabled_skills = set(enabled_skills) if enabled_skills else None
        self.disabled_skills = set(disabled_skills) if disabled_skills else None
        self.sensitive_tools = set(sensitive_tools) if sensitive_tools else None
        # 结构优化：增加 type 字段
        # { skill_id: { "name":..., "type": "global"|"task", "tools": {...} } }
        self.skills = {}
       
        # 全局查找表 (Function Name -> Function Object)
        self.tool_registry = {}
        
        # 1. 加载所有技能
        self._load_all_skills()
        
        # 2. 注册内置控制工具 (activate/exit)
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """注册作为全局工具的控制函数"""
        # 使用 functools.partial 将 self 绑定，避免绑定方法的签名问题
        import functools
        self.tool_registry["activate_skill"] = functools.partial(self._builtin_activate_skill, loader=self)
        self.tool_registry["exit_skill"] = functools.partial(self._builtin_exit_skill, loader=self)


    # === 内置工具实现 (利用 _state 注入) ===
    # 注意：这些是静态方法，避免 self 绑定问题

    @staticmethod
    def _builtin_activate_skill(skill_name: str, _state: Any, loader):
        """
        [Builtin] Activate a specific skill context.
        """
        # 校验 skill_name 是否存在
        if skill_name not in loader.skills:
            return f"Error: Skill '{skill_name}' does not exist. Available: {list(loader.skills.keys())}"

        # 修改状态
        _state.current_intent = skill_name

        # 获取新技能的指令（即时反馈给 LLM）
        # 注意：这里我们不需要 await event，因为我们在 Agent 的 wrapper 层可以监听状态变化
        return f"SYSTEM: Context switched to '{skill_name}'."

    @staticmethod
    def _builtin_exit_skill(_state: Any, loader):
        """
        [Builtin] Exit the current skill and return to routing mode.
        """
        _state.current_intent = None
        return "SYSTEM: Exited skill. Returned to Idle/Routing mode."
    
    
    def _load_all_skills(self):
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir)
            return

        print(f"📂 Scanning skills in '{self.skills_dir}'...")
        
        for folder_name in os.listdir(self.skills_dir):
            if folder_name.startswith('.') or folder_name.startswith('_'): continue
            if self.disabled_skills is not None and folder_name in self.disabled_skills: continue
            if self.enabled_skills is not None and folder_name not in self.enabled_skills: continue

            path = os.path.join(self.skills_dir, folder_name)
            if not os.path.isdir(path): continue

            # 仅处理包含 SKILL.md 的目录 (官方标准)
            if os.path.exists(os.path.join(path, "SKILL.md")):
                self._load_skill_metadata(folder_name, path)

    def _load_skill_metadata(self, folder_name, path):
        """Phase 1: 仅加载元数据和工具函数，不读取 Markdown 正文"""
        try:
            sk_path = os.path.join(path, "SKILL.md")
            # 仅读取 Frontmatter
            sk_data = frontmatter.load(sk_path)
            meta = sk_data.metadata
            
            # 1. 校验名称规范 (Lowercase, hyphens)
            name = meta.get("name", folder_name)
            if not re.match(r'^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$', name):
                 print(f"   ⚠️ Warning: Skill name '{name}' violates official spec (lowercase/hyphens only).")

            description = meta.get("description", "No description provided.")

            skill_type = meta.get("type", "task").lower()
            
            # 2. 加载工具 (核心兼容逻辑)
            # 同时支持官方 scripts/ 和旧版 impl.py
            raw_tools = self._scan_tools_hybrid(folder_name, path)
            
            # 3. 过滤白名单 (allowed-tools)
            allowed = meta.get("allowed-tools", []) or meta.get("allowed_tools", [])
            final_tools = self._filter_tools(raw_tools, allowed)

            # 4. 注册
            self.skills[folder_name] = {
                "name": name,
                "description": description,
                "type": skill_type, # [Saved]
                "path": path,             
                "tools": final_tools,
                "allowed_tools_names": list(final_tools.keys())
            }

            # 更新全局查找表
            self.tool_registry.update(final_tools)
            tag = "[GLOBAL]" if skill_type == "global" else "[Task]"
            print(f"   ✅ {tag} Loaded '{folder_name}' ({len(final_tools)} tools)")

        except Exception as e:
            print(f"   ❌ Error loading '{folder_name}': {e}")

    def _scan_tools_hybrid(self, folder_name, path) -> Dict[str, Any]:
        """
        混合扫描模式：同时兼容官方标准和旧模式
        """
        tools = {}
        
        # 模式 A: 官方标准 (scripts/ 目录)
        scripts_dir = os.path.join(path, "scripts")
        if os.path.exists(scripts_dir) and os.path.isdir(scripts_dir):
            sys.path.insert(0, scripts_dir) # 临时加入 Path 解决引用
            try:
                for file in os.listdir(scripts_dir):
                    if file.endswith(".py") and not file.startswith("_"):
                        # 模块名: skills.<folder>.scripts.<filename>
                        mod_tools = self._import_module(f"skills.{folder_name}.scripts.{file[:-3]}", os.path.join(scripts_dir, file))
                        tools.update(mod_tools)
            finally:
                if scripts_dir in sys.path: sys.path.remove(scripts_dir)

        # 模式 B: 旧版兼容 (根目录 impl.py)
        impl_path = os.path.join(path, "impl.py")
        if os.path.exists(impl_path):
            mod_tools = self._import_module(f"skills.{folder_name}.impl", impl_path)
            # 如果 scripts/ 和 impl.py 有同名函数，impl.py 会覆盖（或者反之，看你偏好）
            tools.update(mod_tools)
            
        return tools

    def _import_module(self, name, path):
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return {n: f for n, f in inspect.getmembers(module, inspect.isfunction) 
                    if not n.startswith("_") and f.__module__ == module.__name__}
        except Exception as e:
            print(f"   ⚠️ Load Error {path}: {e}")
            return {}

    def _filter_tools(self, all_tools, allowed_list):
        if not allowed_list: return all_tools
        return {k: v for k, v in all_tools.items() if k in allowed_list}

    def _func_to_schema(self, func) -> Dict:
        """内部辅助：将 Python 函数转换为 OpenAI Tool Schema"""
        name = func.__name__
        doc = (func.__doc__ or "").strip()
        
        # 这里可以使用 inspect 做更复杂的参数解析，这里简化处理
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": doc,
                "parameters": {
                    "type": "object", 
                    "properties": {}, 
                    "additionalProperties": True # 允许任意参数，生产环境建议用 Pydantic 解析
                }
            }
        }

    # ================= API 供 MicroAgent 调用 =================

    def get_tool_func(self, tool_name: str) -> Optional[callable]:
        """根据名称获取工具函数对象"""
        return self.tool_registry.get(tool_name)

    def get_skill_tools_schema(self, current_skill_id: Optional[str]) -> List[Dict]:
        """获取当前上下文应暴露的工具 Schema"""
        schemas = []
        
        # 1. 始终暴露的全局工具 (如 clipboard)
        # 假设 clipboard 也是一个 skill，或者在此处硬编码判断
        if "read_from_clipboard" in self.tool_registry:
            schemas.append(self._func_to_schema(self.tool_registry["read_from_clipboard"]))
        if "write_to_clipboard" in self.tool_registry:
            schemas.append(self._func_to_schema(self.tool_registry["write_to_clipboard"]))

        
        # 2. 当前 Skill 的专用工具
        if current_skill_id:
            skill_data = self.skills.get(current_skill_id)
            if skill_data:
                for name, func in skill_data['tools'].items():
                    # 避免重复添加
                    if name not in ["read_from_clipboard", "write_to_clipboard"]:
                        schemas.append(self._func_to_schema(func))
        
        return schemas

    def get_available_skills_xml(self) -> str:
        """生成符合官方 Prompt 规范的 XML"""
        parts = ["<available_skills>"]
        for sk_id, data in self.skills.items():
            # [关键] 只有非全局的 Task 才需要展示给 LLM 去选择切换
            if data.get("type") == "global":
                continue
                
            parts.append(f"  <skill>")
            parts.append(f"    <name>{data['name']}</name>")
            parts.append(f"    <description>{data['description']}</description>")
            parts.append(f"    <id>{sk_id}</id>")
            parts.append(f"  </skill>")
        parts.append("</available_skills>")
        return "\n".join(parts)
    
    
    def get_all_tools_schema(self, current_skill_id: Optional[str]) -> List[Dict]:
        """
        根据当前状态，动态组装工具箱：
        1. 内置工具 (activate/exit)
        2. 全局技能 (type=global)
        3. 当前激活的技能 (current_skill_id)
        """
        schemas = []
        added_tool_names = set()
        # Helper: 防止重复添加工具
        def add_tool(func, name_override=None):
            t_name = name_override or func.__name__
            if t_name not in added_tool_names:
                schemas.append(self._func_to_schema(func))
                added_tool_names.add(t_name)
                
        # -------------------------------------------
        # 1. 添加内置控制工具 (Built-in Control)
        # -------------------------------------------
        
        # 构造 activate_skill (动态 Enum)
        skills_xml = self.get_available_skills_xml()
        # 只有 type=task 的技能才需要出现在 activate_skill 的列表中
        # type=global 的技能不需要切过去，因为它们随时可用
        routable_skills = [
            sid for sid, data in self.skills.items() 
            if data.get("type") != "global"
        ]
        
        schemas.append({
            "type": "function",
            "function": {
                "name": "activate_skill",
                "description": f"Switch context to a specialized skill.\nAvailable Skills:\n{skills_xml}",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "skill_name": {"type": "string", "enum": routable_skills} 
                    }, 
                    "required": ["skill_name"]
                }
            }
        })
        added_tool_names.add("activate_skill")

        # 添加 exit_skill
        schemas.append({
            "type": "function", "function": {
                "name": "exit_skill",
                "description": "Exit current skill.",
                "parameters": {"type": "object", "properties": {}}
            }
        })
        added_tool_names.add("exit_skill")
        
        # -------------------------------------------
        # 2. 添加全局技能 (Global Skills)
        # -------------------------------------------
        # 遍历所有已加载的技能，如果是 global，直接加入
        for sk_id, data in self.skills.items():
            if data.get("type") == "global":
                for func in data["tools"].values():
                    add_tool(func)

        # -------------------------------------------
        # 3. 添加当前激活的技能 (Active Context)
        # -------------------------------------------
        if current_skill_id:
            skill_data = self.skills.get(current_skill_id)
            if skill_data:
                for func in skill_data["tools"].values():
                    add_tool(func)
        
        return schemas
    
    
    def get_skill_ids(self) -> List[str]:
        return list(self.skills.keys())

    def load_skill_content(self, skill_id: str) -> str:
        """Lazy Load: 仅在激活时读取 Markdown"""
        if skill_id not in self.skills: return ""
        try:
            sk_path = os.path.join(self.skills[skill_id]["path"], "SKILL.md")
            return frontmatter.load(sk_path).content
        except:
            return ""

    def is_sensitive(self, tool_name: str) -> bool:
        return tool_name in self.sensitive_tools
    
    
    # ================= Prompt 生成逻辑 (View Layer) =================

    def get_context_prompt(self, current_skill_id: Optional[str]) -> str:
        """
        生成与 Skill 相关的 System Prompt 片段。
        包含：
        1. 当前激活的 Skill 指令 (或 Idle 状态说明)
        2. 路由协议 (告诉 LLM 如何使用 activate_skill/exit_skill)
        """
        
        # Part A: 状态上下文 (State Context)
        context_str = ""
        if current_skill_id:
            # [Active Mode] 加载具体技能的正文
            instruction = self.load_skill_content(current_skill_id)
            if instruction:
                context_str = (
                    f"\n\n=== 🛡️ ACTIVE SKILL: {current_skill_id} ===\n"
                    f"{instruction}\n"
                    f"(⚠️ CRITICAL: You are strictly bound by the instructions above. "
                    f"Focus ONLY on this skill's domain.)"
                )
            else:
                context_str = f"\n\n=== 🛡️ ACTIVE SKILL: {current_skill_id} (Instructions Missing) ==="
        else:
            # [Idle Mode] 路由模式
            context_str = (
                "\n\n=== 🧭 STATUS: IDLE (Routing Mode) ===\n"
                "You are currently in the main hub. Analyze the user's request.\n"
                "- If it matches a specific skill description, activate it.\n"
                "- If it requires general knowledge or planning, handle it directly."
            )

        # Part B: 路由协议 (Routing Protocol)
        # 因为 activate_skill/exit_skill 是 Loader 提供的，所以说明书也由 Loader 提供
        routing_protocol = """
\n=== 🔀 ROUTING & TOOL USE PROTOCOL ===
1. **Discovery**: Check the `activate_skill` tool definition to see available skills.
2. **Switching**: If a user's request matches a skill's description better than your current state, call `activate_skill(skill_name=...)` IMMEDIATELY.
3. **Exiting**: When the specific task defined by the skill is complete, call `exit_skill()`.
4. **Anti-Hallucination**: Do NOT call the skill name (e.g. `asset_search()`) as a function. Only use the tools explicitly provided in the tools schema.
"""

        return context_str + routing_protocol