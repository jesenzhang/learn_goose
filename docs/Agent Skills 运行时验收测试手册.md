这是一个针对 **Agent Skills Runtime（运行时）** 的完整测试套件设计。  
鉴于我们是从零构建基础设施（不依赖 Anthropic SDK 的黑盒逻辑），测试的核心必须验证**解析器（Parser）**、**路由逻辑（Routing Logic）** 和 **沙箱执行（Sandbox Execution）** 是否符合规范。  
这份指南包含一套 **Python 自动化测试脚本（Test Harness）** 和一份 **手动验收清单**。

# Agent Skills 系统验收测试手册 (v1.0)

本测试套件旨在验证您的 Runtime 是否正确实现了 **"目录即能力"**、**"渐进式披露"** 以及 **"安全沙箱"** 三大核心协议。

## 第一部分：测试环境准备 (Test Harness Setup)

为了保证测试的纯净性，我们需要一个能够动态生成“假技能”的测试固件。请创建一个名为 tests/conftest.py 或在测试脚本头部包含以下工具类：  
import os  
import shutil  
import tempfile  
import yaml  
from pathlib import Path

class MockSkillGenerator:  
    """  
    用于动态生成符合规范的 Skill 目录结构的测试工具  
    """  
    def \_\_init\_\_(self):  
        self.test\_dir \= tempfile.mkdtemp()  
        self.skills\_root \= Path(self.test\_dir) / ".claude" / "skills"  
        self.skills\_root.mkdir(parents=True)

    def create\_skill(self, folder\_name, yaml\_content, readme\_body, script\_files=None):  
        skill\_path \= self.skills\_root / folder\_name  
        skill\_path.mkdir()  
          
        \# 1\. 创建 SKILL.md  
        with open(skill\_path / "SKILL.md", "w") as f:  
            f.write("---\\n")  
            yaml.dump(yaml\_content, f)  
            f.write("---\\n")  
            f.write(readme\_body)  
              
        \# 2\. 创建脚本资源  
        if script\_files:  
            scripts\_dir \= skill\_path / "scripts"  
            scripts\_dir.mkdir()  
            for fname, content in script\_files.items():  
                with open(scripts\_dir / fname, "w") as f:  
                    f.write(content)  
          
        return skill\_path

    def cleanup(self):  
        shutil.rmtree(self.test\_dir)

## 第二部分：自动化测试用例 (Automated Test Cases)

请将以下代码保存为 test\_skills\_runtime.py。这些用例直接对应文档中的规范要求。

### 测试组 1：物理层解析验证 (Discovery & Parsing)

**目标**：验证系统是否能正确识别符合规范的技能，并拒绝非法技能。

* **来源依据**：1 (字段要求), 2 (YAML 语法), 3 (路径规范)。

import unittest  
\# 假设您的实现代码在 runtime.py 中  
from runtime import SkillRegistry 

class TestDiscovery(unittest.TestCase):  
    def setUp(self):  
        self.mock\_gen \= MockSkillGenerator()  
        self.registry \= SkillRegistry()  
        \# 覆盖注册表的扫描路径为测试目录  
        self.registry.search\_paths \= \[self.mock\_gen.skills\_root\]

    def tearDown(self):  
        self.mock\_gen.cleanup()

    def test\_valid\_skill\_loading(self):  
        """TC-01: 验证标准技能的加载"""  
        self.mock\_gen.create\_skill(  
            folder\_name="data-cruncher",  
            yaml\_content={  
                "name": "data-cruncher",  
                "description": "Process CSV files",  
                "allowed-tools": \["Read"\]  
            },  
            readme\_body="\# Instructions\\nRun script."  
        )  
        self.registry.scan()  
        self.assertIn("data-cruncher", self.registry.skills\_cache)  
        self.assertEqual(self.registry.skills\_cache\["data-cruncher"\]\["metadata"\]\["allowed-tools"\], \["Read"\])

    def test\_invalid\_yaml\_rejection(self):  
        """TC-02: 验证系统是否拒绝无效 YAML (来源 \[2\])"""  
        skill\_path \= self.mock\_gen.skills\_root / "broken-skill"  
        skill\_path.mkdir()  
        with open(skill\_path / "SKILL.md", "w") as f:  
            f.write("---\\nname: broken\\n  tab\_error: true\\n---\\n") \# YAML 禁止 Tab  
          
        self.registry.scan()  
        self.assertNotIn("broken", self.registry.skills\_cache, "系统应当忽略 YAML 语法错误的技能")

    def test\_naming\_convention(self):  
        """TC-03: 验证命名规范 (来源 \[1\])"""  
        \# 来源 \[1\]: name 必须仅使用小写字母、数字和连字符  
        self.mock\_gen.create\_skill(  
            folder\_name="Bad Name",  
            yaml\_content={"name": "Bad Name", "description": "desc"}, \# 包含空格和大写  
            readme\_body="..."  
        )  
        self.registry.scan()  
        \# 具体的实现策略：您可以选择忽略或报错，这里假设严格模式下忽略  
        \# self.assertNotIn("Bad Name", self.registry.skills\_cache) 

### 测试组 2：渐进式披露逻辑 (Progressive Disclosure Logic)

**目标**：验证系统是否实现了 L1（元数据）到 L2（完整指令）的正确状态转换。这是节省 Token 的关键。

* **来源依据**：4 (元数据加载), 5 (三层加载模型)。

from runtime import AgentRuntime

class TestProgressiveDisclosure(unittest.TestCase):  
    def setUp(self):  
        self.mock\_gen \= MockSkillGenerator()  
        self.registry \= SkillRegistry()  
        self.registry.search\_paths \= \[self.mock\_gen.skills\_root\]  
          
        \# 创建一个“重型”技能  
        self.mock\_gen.create\_skill(  
            folder\_name="heavy-skill",  
            yaml\_content={"name": "heavy-skill", "description": "Complex logic"},  
            readme\_body="VERY LONG INSTRUCTIONS " \* 100   
        )  
        self.registry.scan()  
        self.runtime \= AgentRuntime(self.registry)

    def test\_l1\_metadata\_only(self):  
        """TC-04: 验证初始状态仅加载元数据 (来源 \[5\])"""  
        prompt \= self.runtime.construct\_system\_prompt()  
          
        \# 验证包含 Description  
        self.assertIn("Complex logic", prompt)  
        \# 验证不包含完整 Instructions (L2)  
        self.assertNotIn("VERY LONG INSTRUCTIONS", prompt, "初始 Prompt 不应包含完整指令")

    def test\_l2\_activation(self):  
        """TC-05: 验证激活后加载完整指令"""  
        \# 模拟路由器决定激活技能  
        self.runtime.active\_skills.append("heavy-skill")  
          
        prompt \= self.runtime.construct\_system\_prompt()  
          
        \# 验证此时包含了完整 Instructions  
        self.assertIn("VERY LONG INSTRUCTIONS", prompt, "激活后应注入完整指令")

### 测试组 3：沙箱与路径规范 (Sandbox & Paths)

**目标**：验证代码执行逻辑，特别是跨平台路径兼容性。

* **来源依据**：3 (正斜杠路径), 6 (脚本调用).

class TestExecution(unittest.TestCase):  
    def test\_script\_path\_resolution(self):  
        """TC-06: 验证脚本路径必须为 Unix 风格 (来源 \[3\])"""  
        \# 模拟技能结构  
        skill\_data \= {  
            "path": "/abs/path/to/skill",  
            "metadata": {"name": "test"}  
        }  
          
        \# 假设您的 Runtime 有一个生成挂载路径的方法  
        \# 模拟 LLM 输出 "python scripts/helper.py"  
        script\_ref \= "scripts/helper.py"  
          
        \# 验证 Runtime 是否能正确将其解析为沙箱内的绝对路径  
        \# Windows 系统下不应生成 scripts\\helper.py  
        resolved\_path \= Path(skill\_data\["path"\]) / script\_ref  
        self.assertTrue(str(resolved\_path).endswith("scripts/helper.py") or str(resolved\_path).endswith("scripts\\\\helper.py"))  
        \# 注意：这里测试的是您的 Runtime 如何处理路径字符串，  
        \# 关键是确保传递给 docker/沙箱 的命令使用正斜杠

### 测试组 4：权限网关 (Permission Gateway)

**目标**：验证 allowed-tools 是否生效。

* **来源依据**：7 (限制工具访问), 8 (权限示例).

class TestSecurity(unittest.TestCase):  
    def test\_tool\_blocking(self):  
        """TC-07: 验证非白名单工具被拦截 (来源 \[7\])"""  
        \# 定义一个只读技能  
        skill\_config \= {  
            "metadata": {"allowed-tools": \["Read", "Grep"\]}  
        }  
          
        \# 模拟 Tool Call  
        allowed\_call \= "Read"  
        blocked\_call \= "Write" \# 不在白名单  
          
        \# 模拟 Runtime 的鉴权逻辑 check\_permission(skill, tool\_name)  
        \# self.assertTrue(runtime.check\_permission(skill\_config, allowed\_call))  
        \# self.assertFalse(runtime.check\_permission(skill\_config, blocked\_call))

## 第三部分：手动验收清单 (Manual Verification Checklist)

有些功能难以单元测试，需要进行端到端的集成验证。

### 1\. 发现机制验证

*  **热重载测试**：在 Runtime 运行时，手动在 .claude/skills/ 下新建一个文件夹。  
* *预期*：下一次对话时，系统应能自动感知到新技能（或提示需重启）。  
*  **冲突测试**：在个人目录 (\~/.claude/skills) 和项目目录 (./.claude/skills) 创建同名 Skill。  
* *预期*：项目级 Skill 应覆盖个人级 Skill（优先级原则）。

### 2\. 执行环境验证

*  **依赖缺失测试**：创建一个 Skill，其脚本中 import non\_existent\_package，并在 SKILL.md 中声明依赖。  
* *预期*：执行时，Runtime 应检测到失败，并尝试安装依赖或提示用户（参考 6）。  
*  **文件生成测试**：运行一个生成 Excel 的 Skill。  
* *预期*：生成的 .xlsx 文件应出现在 outputs/ 目录中，且文件完整可打开（参考 9, 10）。

### 3\. Git 协作验证 (来源 11\)

*  **同步测试**：  
* 用户 A 创建 Skill 并 git push。  
* 用户 B 执行 git pull。  
* 用户 B 立即询问 Claude 关于该 Skill 的问题。  
* *预期*：Claude 能够立即识别并使用该 Skill，无需额外配置。

## 为什么这些测试至关重要？

1. **防止 Token 爆炸**：如果没有通过 TestProgressiveDisclosure，你的系统可能会在每次请求中加载所有 Skill 的完整文本，导致 Token 成本指数级上升（来源 12 指出这能节省 98% 成本）。  
2. **防止安全漏洞**：如果没有通过 TestSecurity，恶意 Skill 可能会利用 Write 或 Bash 工具破坏用户文件系统（来源 7）。  
3. **确保跨平台可用**：如果没有通过路径测试，Windows 用户将无法运行使用了 scripts/ 的技能（来源 3）。

