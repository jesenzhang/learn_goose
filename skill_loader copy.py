import os
import frontmatter # 专门解析 YAML Frontmatter
import importlib.util
from typing import Dict, Any, List

class AnthropicSkillLoader:
    def __init__(self, skills_dir="agent_skills", enabled_skills=None):
        self.skills_dir = skills_dir
        self.enabled_skills = set(enabled_skills) if enabled_skills else None
        self.skills = {} # 存储加载的技能数据
        self.global_tools = {} # 所有技能的工具集合
        
        self._load_all_skills()

    def _load_all_skills(self):
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir)
            return

        for skill_name in os.listdir(self.skills_dir):
            if skill_name.startswith('.'):
                continue
            
            if self.enabled_skills is not None and skill_name not in self.enabled_skills:
                print(f"🚫 Skill '{skill_name}' is disabled in config. Skipped.")
                continue
            
            path = os.path.join(self.skills_dir, skill_name)
            if os.path.isdir(path):
                self._load_single_skill(skill_name, path)

    def _load_single_skill(self, folder_name, path):
        md_path = os.path.join(path, "SKILL.md")
        scripts_path = os.path.join(path, "scripts")
        py_path = os.path.join(path, "impl.py")

        if not os.path.exists(md_path):
            return

        print(f"📦 Loading Skill: {folder_name} ...")

        # 1. 解析 SKILL.md (Frontmatter + Body)
        try:
            skill_data = frontmatter.load(md_path)
            metadata = skill_data.metadata
            content = skill_data.content
        except Exception as e:
            print(f"   ❌ Error parsing SKILL.md: {e}")
            return

        # 获取关键元数据
        name = metadata.get("name", folder_name)
        description = metadata.get("description", "No description provided.")
        allowed_tools = metadata.get("allowed-tools", []) # 标准字段

        # 2. 加载 Python 实现 (impl.py)
        tools_map = {}
        if os.path.exists(py_path):
            spec = importlib.util.spec_from_file_location(f"skills.{folder_name}", py_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 注册工具
            for func_name in dir(module):
                func = getattr(module, func_name)
                if callable(func) and not func_name.startswith("_"):
                    tools_map[func_name] = func
                    self.global_tools[func_name] = func # 注册到全局池

        # 3. 存储技能对象
        self.skills[name] = {
            "name": name,
            "description": description,
            "instruction": content, # Markdown 正文
            "tools": tools_map,
            "allowed_tools_names": allowed_tools
        }
        
        print(f"   ✅ Loaded '{name}' with {len(tools_map)} tools.")

    def get_skill_description_list(self) -> str:
        """生成供 Agent 路由使用的技能列表描述"""
        lines = []
        for name, data in self.skills.items():
            lines.append(f"- {name}: {data['description']}")
        return "\n".join(lines)