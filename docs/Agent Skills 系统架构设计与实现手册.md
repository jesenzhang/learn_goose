这是一份针对**Agent Skills 系统架构**的深度设计与实现手册。  
本手册不假设你直接调用现成的 SDK，而是从**系统工程**的角度，解构如何从零搭建一个支持“程序性知识（Procedural Knowledge）”的 Agent 运行时环境（Runtime）。这包括文件系统的解析标准、上下文管理的底层逻辑、以及必须构建的沙箱基础设施。

# Agent Skills 系统架构设计与实现手册 (v1.0)

**目标读者**：系统架构师、Agent 平台工程师**设计目标**：构建一个去中心化、安全、支持“渐进式披露”的 Agent 技能运行时。

## 第一部分：物理层——标准目录结构规范 (The Physical Specification)

在 Skills 架构中，文件系统不仅仅是存储，它是**接口定义语言 (IDL)**。系统必须严格按照以下规范解析目录，否则视为无效技能。

### 1\. 单元定义：目录即技能 (Directory-as-Capability)

Skill **必须**是一个独立的目录，严禁使用单文件形式。目录名称即为技能的 Slug（系统内部ID）。

* **路径规范**：系统必须监听以下标准路径 1, 2：  
* 用户级：\~/.claude/skills/ (全局可用)  
* 项目级：./.claude/skills/ (仅当前上下文可用，需支持 Git 同步 3\)  
* **命名约束**：目录名必须符合 kebab-case（仅限小写字母、数字、连字符），长度 \< 64 字符 4。

### 2\. 入口文件：SKILL.md 解析标准

这是系统必须首先读取的“引导扇区”。

#### A. 元数据头 (YAML Frontmatter)

系统解析器必须提取位于文件顶部的 YAML 块（由 \--- 包裹）。

* **Schema 定义**：  
* \---  
* name: \[String, 必填\]          \# 必须与目录名语义一致  
* description: \[String, 必填\]   \# 系统的核心路由依据。必须包含"做什么"和"触发条件"。最大 1024 字符。  
* allowed-tools: \[List, 可选\]   \# 权限控制。例如 \[Read, Grep\]。系统需据此生成拦截策略。  
* version: \[String, 推荐\]       \# 语义化版本，用于缓存控制。  
* \---  
* **解析规则**：  
* 必须校验 YAML 语法（禁止 Tab 缩进）5, 6。  
* 若缺少 name 或 description，系统应在加载阶段抛出异常，拒绝注册该 Skill。

#### B. 指令体 (Instruction Body)

YAML 之后的所有 Markdown 内容。

* **系统处理逻辑**：系统不应立即读取此部分。仅在路由命中后，才将其作为 System Prompt 的一部分注入。

### 3\. 资源文件结构 (Resource Topology)

为了支持代码执行，目录内部必须遵循特定的拓扑结构 7, 8：  
skill-root/  
├── SKILL.md            \# \[L1/L2\] 入口  
├── reference.md        \# \[L3\] 静态文档 (系统仅在 Agent 请求读取时加载)  
├── scripts/            \# \[L3\] 可执行逻辑  
│   ├── helper.py       \# 必须使用 Unix 风格路径引用 (scripts/helper.py) \[9\]  
│   └── requirements.txt \# 依赖声明 (系统需解析此文件并在沙箱预装依赖)  
└── templates/          \# \[L3\] 静态资源

## 第二部分：逻辑层——渐进式披露实现机制 (Progressive Disclosure Logic)

“渐进式披露”是本架构的核心，旨在解决 Token 预算与技能数量之间的矛盾。系统必须实现一个**三级上下文状态机**。

### 状态 1：感知态 (Awareness State) \- L1

1. **触发时机**：Agent 初始化或会话开始时。  
2. **系统行为**：  
3. 扫描所有标准路径下的 SKILL.md。  
4. 仅提取 YAML 中的 description 和 name。  
5. 构造一个轻量级的 System Prompt 注入给 LLM：“你拥有以下能力：Skill Name: Description...”。  
6. **数据量**：极低（每个技能约 100 tokens）10, 11。

### 状态 2：激活态 (Activation State) \- L2

1. **触发时机**：LLM 的输出表明它意图使用某项技能（系统需通过语义路由或 Tool Call 捕获此意图）。  
2. **系统行为**：  
3. 系统锁定目标 Skill 目录。  
4. 读取 SKILL.md 的完整 Markdown 内容。  
5. 将此内容**动态注入**到当前的上下文窗口中（作为临时的 System Instruction 或 User Context）。  
6. **数据量**：中等（\< 5k tokens）10。

### 状态 3：执行态 (Execution State) \- L3

1. **触发时机**：LLM 生成代码试图调用 scripts/ 下的文件，或读取 reference.md。  
2. **系统行为**：  
3. **文件系统映射**：系统必须将该 Skill 目录挂载到代码执行沙箱的特定路径下。  
4. **依赖加载**：系统检测到执行请求时，需确保环境满足依赖（如 pip install）。  
5. **懒加载读取**：如果 LLM 请求读取 reference.md，系统调用文件读取工具返回内容。  
6. **数据量**：按需消耗 7, 12。

## 第三部分：基础设施层——Agent Runtime 必须实现的底层能力

如果你从零构建 Runtime，**不能**仅仅依赖 LLM 的聊天接口。你必须构建以下三个基础设施组件，否则 Skills 无法运行。

### 1\. 隔离沙箱 (The Execution Sandbox)

Skills 的核心价值在于执行代码（尤其是 Python）13。

* **强制要求**：Runtime 必须集成一个代码执行环境（如 Docker 容器、Firecracker microVM 或 gVisor）。  
* **网络策略**：  
* 默认应隔离网络，除非明确授权（MCP 负责数据连接，Skill 负责数据处理 14）。  
* 必须允许访问 PyPI 镜像源以安装依赖 8。  
* **文件系统挂载**：  
* 当 Skill 激活时，Runtime 必须将该 Skill 的目录（包含 scripts/）**只读挂载**到沙箱的工作目录中。  
* LLM 生成的 Python 代码必须能以相对路径 scripts/helper.py 访问这些文件 9。

### 2\. 虚拟文件系统与工件交付 (VFS & Artifact Delivery)

Skill 执行的结果往往是文件（PDF, Excel）。LLM 本身无法传输二进制流。

* **实现要求**：  
* Runtime 需提供一个 /mnt/outputs 或类似的可写目录给沙箱。  
* **Sidecar 进程**：监控该目录，一旦有文件生成，立即将其上传至对象存储（S3/MinIO）。  
* **协议转换**：将上传后的文件转换为 file\_id 或下载链接，回传给 LLM 的上下文 15, 16。

### 3\. 工具拦截与权限网关 (Tool Interceptor)

实现 allowed-tools 的逻辑 17。

* **实现要求**：  
* 在 LLM 发起 Tool Call 之前，Runtime 必须拦截请求。  
* **鉴权逻辑**：检查当前激活的 Skill SKILL.md 中的 allowed-tools 列表。  
* 如果请求的工具（如 Bash）不在白名单（如仅允许 Read, Grep），Runtime 必须直接拒绝执行并返回 PermissionError，而不是透传给沙箱。

## 第四部分：Python 原型设计 (从零构建 Skill Orchestrator)

以下代码不使用 Anthropic SDK 的高级封装，而是展示**如何手写一个 Skill 管理器**，模拟系统侧的解析、路由和上下文注入逻辑。

### 1\. 目录扫描与解析器 (The Indexer)

import os  
import yaml  
from pathlib import Path  
from typing import Dict, Optional, List

class SkillRegistry:  
    def \_\_init\_\_(self):  
        self.skills\_cache: Dict\[str, dict\] \= {}  
        \# 定义标准扫描路径 \[1, 2\]  
        self.search\_paths \= \[  
            Path.home() / ".claude/skills",  
            Path("./.claude/skills")  
        \]

    def scan(self):  
        """物理层：扫描并校验所有 Skill"""  
        print("🔍 Scanning for skills...")  
        for base\_path in self.search\_paths:  
            if not base\_path.exists():  
                continue  
              
            \# 遍历一级子目录  
            for skill\_dir in base\_path.iterdir():  
                if skill\_dir.is\_dir():  
                    self.\_load\_skill(skill\_dir)

    def \_load\_skill(self, skill\_dir: Path):  
        """解析 SKILL.md \[4, 5\]"""  
        manifest\_path \= skill\_dir / "SKILL.md"  
        if not manifest\_path.exists():  
            return

        try:  
            \# 手动分离 Frontmatter 和 Body  
            with open(manifest\_path, 'r', encoding='utf-8') as f:  
                content \= f.read()  
              
            if not content.startswith("---"):  
                return \# 无效格式

            parts \= content.split("---", 2\)  
            if len(parts) \< 3:  
                return \# 格式错误

            \# 解析 YAML  
            metadata \= yaml.safe\_load(parts\[18\])  
            body \= parts\[19\].strip()

            \# 校验必须字段 \[4\]  
            if not metadata.get('name') or not metadata.get('description'):  
                print(f"⚠️ Invalid skill at {skill\_dir}: Missing name or description")  
                return

            \# 注册到内存  
            skill\_id \= metadata\['name'\]  
            self.skills\_cache\[skill\_id\] \= {  
                "path": str(skill\_dir),  
                "metadata": metadata,  
                "instructions": body  \# L2 数据  
            }  
            print(f"✅ Loaded skill: {skill\_id}")

        except Exception as e:  
            print(f"❌ Error loading {skill\_dir}: {e}")

    def get\_discovery\_prompt(self) \-\> str:  
        """L1 阶段：生成轻量级索引供 LLM 感知 \[10\]"""  
        prompt \= "You have the following skills available. Use them when relevant:\\n"  
        for skill\_id, data in self.skills\_cache.items():  
            desc \= data\['metadata'\]\['description'\]  
            prompt \+= f"- {skill\_id}: {desc}\\n"  
        return prompt

### 2\. 运行时上下文管理器 (Runtime Orchestrator)

这个类模拟了 Agent Runtime 如何处理用户的 Prompt，并决定是否“挂载”技能。  
class AgentRuntime:  
    def \_\_init\_\_(self, registry: SkillRegistry):  
        self.registry \= registry  
        self.active\_skills \= \[\] \# 当前上下文激活的技能

    def construct\_system\_prompt(self) \-\> str:  
        """构造动态 System Prompt"""  
        \# 1\. 基础指令  
        base\_prompt \= "You are a helpful agent. "  
          
        \# 2\. L1 级披露：告知有哪些技能可用  
        base\_prompt \+= self.registry.get\_discovery\_prompt()  
          
        \# 3\. L2 级披露：注入已激活技能的完整指令 \[12\]  
        if self.active\_skills:  
            base\_prompt \+= "\\n\\n=== ACTIVATED SKILLS INSTRUCTIONS \===\\n"  
            for skill\_id in self.active\_skills:  
                skill\_data \= self.registry.skills\_cache.get(skill\_id)  
                if skill\_data:  
                    base\_prompt \+= f"\\n\#\# Skill: {skill\_id}\\n"  
                    base\_prompt \+= skill\_data\['instructions'\]  
                    \# 提示 LLM 脚本位置  
                    base\_prompt \+= f"\\n(Scripts are mounted at: {skill\_data\['path'\]}/scripts/)\\n"  
          
        return base\_prompt

    def mock\_inference\_loop(self, user\_query: str):  
        """  
        模拟 LLM 推理循环 (Pseudo-code for logic demonstration)  
        这部分逻辑通常由 LLM 引擎内部的 Router 完成  
        """  
        print(f"\\n👤 User: {user\_query}")  
          
        \# 步骤 1: 简单的语义匹配逻辑 (模拟 LLM 决策)  
        \# 实际系统中，这不仅是关键词匹配，而是 LLM 理解后的 Tool Call  
        detected\_skill \= None  
        for skill\_id, data in self.registry.skills\_cache.items():  
            \# 简单的模拟：如果 Query 包含 Description 中的关键词  
            keywords \= data\['metadata'\]\['description'\].split()  
            if any(k.lower() in user\_query.lower() for k in keywords if len(k) \> 4):  
                detected\_skill \= skill\_id  
                break  
          
        \# 步骤 2: 动态激活 (L2 Loading)  
        if detected\_skill and detected\_skill not in self.active\_skills:  
            print(f"🚀 Intent detected. Activating skill: {detected\_skill}")  
            self.active\_skills.append(detected\_skill)  
            \# 重新构造 Prompt，包含详细指令  
            final\_prompt \= self.construct\_system\_prompt()  
            print("🔄 System Prompt Updated (Instructions Injected)")  
        else:  
            final\_prompt \= self.construct\_system\_prompt()

        \# 步骤 3: 模拟执行 (L3 Execution)  
        \# 假设 LLM 输出："Run scripts/analyze.py"  
        \# Runtime 需要拦截并执行  
        if detected\_skill:  
            self.\_execute\_sandbox(detected\_skill)

    def \_execute\_sandbox(self, skill\_id):  
        """基础设施层：模拟沙箱挂载与执行 \[13\]"""  
        skill\_path \= self.registry.skills\_cache\[skill\_id\]\['path'\]  
        scripts\_path \= os.path.join(skill\_path, "scripts")  
          
        print(f"📦 \[Sandbox\] Mounting volume: {skill\_path} \-\> /mnt/skill")  
        print(f"🔧 \[Sandbox\] Checking allowed-tools: {self.registry.skills\_cache\[skill\_id\]\['metadata'\].get('allowed-tools', 'ALL')}")  
          
        \# 检查依赖  
        req\_file \= os.path.join(skill\_path, "requirements.txt") \# 假设在根目录或 scripts 下  
        if os.path.exists(req\_file):  
            print(f"📦 \[Sandbox\] Installing dependencies from {req\_file}...")  
          
        \# 模拟执行脚本  
        print(f"▶️ \[Sandbox\] Executing: python {scripts\_path}/helper.py")   
        \# 实际代码应使用 subprocess.run 或 Docker SDK

\# \--- 启动测试 \---  
if \_\_name\_\_ \== "\_\_main\_\_":  
    \# 1\. 初始化并扫描  
    registry \= SkillRegistry()  
    registry.scan()  
      
    \# 2\. 启动运行时  
    runtime \= AgentRuntime(registry)  
      
    \# 3\. 模拟用户请求  
    \# 假设有一个名为 'pdf-processor' 的技能，描述为 'Extract text from PDF'  
    runtime.mock\_inference\_loop("Please help me extract text from this PDF document.")

### 3\. 实现检查清单 (Checklist for Engineers)

在部署这套系统前，请确认以下基础设施已就绪：

1. **YAML 解析器健壮性**：能否处理非标字符？能否在缺失字段时优雅降级？  
2. **路径安全性**：是否校验了 scripts/../../etc/passwd 这种路径穿越攻击？（必须在沙箱层面封死）。  
3. **状态清理**：一次会话结束后，是否清空了 active\_skills 列表，防止上下文污染？  
4. **超时控制**：代码执行沙箱必须有严格的 Timeout 设置（如 30秒），防止死循环脚本阻塞 Runtime。

