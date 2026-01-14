import os
import re
import datetime
import subprocess
from pathlib import Path

# ==========================================
# 🛠️ Configuration & Constants
# ==========================================

# 基础路径配置
# BASE_DIR: 目标项目根目录 (Agent 正在操作的地方)
BASE_DIR = Path(os.getcwd())
CONDUCTOR_DIR = BASE_DIR / "conductor"
TRACKS_FILE = CONDUCTOR_DIR / "tracks.md"

# SKILL_DIR: 当前 Skill 所在的目录 (用于加载 prompts)
SKILL_DIR = Path(__file__).parent
PROMPTS_DIR = SKILL_DIR / "prompts"

# ==========================================
# 📄 Embedded Templates (Fallbacks)
# ==========================================

TEMPLATE_PRODUCT = """# Product Context
## Vision
[Describe the high-level vision here]

## Core Goals
1. [Goal A]
2. [Goal B]
"""

TEMPLATE_WORKFLOW = """# Workflow
1. **Plan**: Break down task in plan.md
2. **Test**: Write a failing test (Red)
3. **Implement**: Make it pass (Green)
4. **Refactor**: Clean up
"""

TEMPLATE_TECH_STACK = """# Tech Stack
- Language: [e.g. Python]
- Framework: [e.g. Flask]
"""

TEMPLATE_PLAN_HEADER = """
- [ ] **Phase 1: Setup**
    - [ ] Define interfaces
- [ ] **Phase 2: Implementation**
    - [ ] Core logic
- [ ] **Phase 3: Testing**
    - [ ] Unit tests
"""

# ==========================================
# 🧠 Helper Functions
# ==========================================

def _read_prompt(prompt_name: str) -> str:
    """Helper to load external protocol prompts to guide the Agent."""
    prompt_path = PROMPTS_DIR / prompt_name
    if prompt_path.exists():
        content = prompt_path.read_text(encoding="utf-8")
        return f"\n\n--- [SYSTEM PROTOCOL: {prompt_name}] ---\n{content}\n---------------------------------------\n"
    return ""

def _write_if_missing(path: Path, content: str):
    """Helper to write a file only if it doesn't exist."""
    if not path.exists():
        path.write_text(content, encoding='utf-8')

# ==========================================
# 🚀 Tool Functions
# ==========================================

def setup_conductor(project_name: str = "My Project"):
    """
    Initialize the Conductor folder structure (conductor/) and base files.
    Run this first for any new project. 
    Returns the 'Setup Protocol' which the Agent must follow next.
    """
    try:
        if CONDUCTOR_DIR.exists():
            # 即使文件夹存在，也返回 Setup Protocol，以防用户想重新配置
            protocol = _read_prompt("setup_prompt.md")
            return f"Info: 'conductor/' directory already exists.\n{protocol}"

        os.makedirs(CONDUCTOR_DIR / "tracks", exist_ok=True)

        # Create base files with templates
        _write_if_missing(CONDUCTOR_DIR / "product.md", f"# {project_name}\n\n{TEMPLATE_PRODUCT}")
        _write_if_missing(CONDUCTOR_DIR / "tech-stack.md", TEMPLATE_TECH_STACK)
        _write_if_missing(CONDUCTOR_DIR / "workflow.md", TEMPLATE_WORKFLOW)
        _write_if_missing(CONDUCTOR_DIR / "tracks.md", "# Active Tracks\n\nNo tracks yet.")

        # Load the Setup Protocol logic from the external file
        protocol = _read_prompt("setup_prompt.md")

        return (
            f"✅ Success: Conductor initialized in {CONDUCTOR_DIR}.\n"
            f"Please proceed immediately to the **Product Definition** phase using the protocol below.\n"
            f"{protocol}"
        )
    except Exception as e:
        return f"Error setting up conductor: {str(e)}"

def create_track(title: str, description: str, type: str = "feature"):
    """
    Create a new development track. 
    Generates a folder in conductor/tracks/ with spec.md and plan.md.
    """
    try:
        if not CONDUCTOR_DIR.exists():
            return "Error: Conductor not initialized. Please run setup_conductor() first."

        # Generate specific ID: e.g., feature_20240101_user_login
        timestamp = datetime.datetime.now().strftime("%Y%m%d")
        safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title).lower()[:30]
        track_id = f"{type}_{timestamp}_{safe_title}"

        track_path = CONDUCTOR_DIR / "tracks" / track_id
        os.makedirs(track_path, exist_ok=True)

        # Write Spec
        spec_content = f"# Spec: {title}\n\n## Context\n{description}\n"
        (track_path / "spec.md").write_text(spec_content, encoding="utf-8")

        # Write Plan
        plan_content = f"# Plan: {title}\n{TEMPLATE_PLAN_HEADER}"
        (track_path / "plan.md").write_text(plan_content, encoding="utf-8")

        # Append to tracks.md
        with open(TRACKS_FILE, "a", encoding="utf-8") as f:
            entry = f"\n- [ ] **{title}** (`{track_id}`) - {type}"
            f.write(entry)

        return (
            f"✅ Success: Created track '{track_id}'.\n"
            f"Files created:\n"
            f"- {track_path}/spec.md\n"
            f"- {track_path}/plan.md\n\n"
            f"👉 NEXT STEP: Read `plan.md` and refine the tasks before implementing."
        )
    except Exception as e:
        return f"Error creating track: {str(e)}"

def get_conductor_status(track_id: str = None):
    """
    Get the overall status (tracks list) or the detailed plan of a specific track.
    """
    try:
        # Load the Status Protocol to guide how the Agent summarizes the output
        protocol = _read_prompt("status_prompt.md")
        
        if not track_id:
            # Return global status
            if TRACKS_FILE.exists():
                content = TRACKS_FILE.read_text(encoding='utf-8')
                return f"=== Project Tracks ===\n{content}\n\n{protocol}"
            return "Conductor not initialized."
        
        # Return specific track plan
        plan_path = CONDUCTOR_DIR / "tracks" / track_id / "plan.md"
        if plan_path.exists():
            content = plan_path.read_text(encoding='utf-8')
            return f"=== Plan for {track_id} ===\n{content}\n\n{protocol}"
            
        return f"Error: Track '{track_id}' not found."
    except Exception as e:
        return f"Error reading status: {str(e)}"

def update_task_status(track_id: str, task_snippet: str, status: str = "done"):
    """
    Updates a task in a plan.md. 
    Searches for the task_snippet and marks it [x] (done) or [ ] (todo).
    """
    try:
        plan_path = CONDUCTOR_DIR / "tracks" / track_id / "plan.md"
        if not plan_path.exists():
            return f"Error: Plan for {track_id} not found."

        content = plan_path.read_text(encoding='utf-8')
        mark = "[x]" if status == "done" else "[ ]"
        
        # 简单的字符串匹配和替换逻辑
        # 更加健壮的实现会使用正则来匹配 "- [ ]" 和 "- [x]"
        if task_snippet in content:
            lines = content.split('\n')
            new_lines = []
            updated = False
            
            # 正则匹配 Markdown check box: - [ ] 或 - [x]
            # 这里的逻辑是：如果在这一行里找到了 snippet，且这一行看起来像是个 task，就更新它
            checkbox_pattern = re.compile(r"-\s*\[([ x])\]")
            
            for line in lines:
                if task_snippet in line and checkbox_pattern.search(line):
                    new_line = checkbox_pattern.sub(f"- {mark}", line)
                    new_lines.append(new_line)
                    updated = True
                else:
                    new_lines.append(line)
            
            if updated:
                plan_path.write_text('\n'.join(new_lines), encoding='utf-8')
                return f"Success: Marked task containing '{task_snippet}' as {status}."
            else:
                return f"Warning: Found snippet '{task_snippet}' but couldn't locate a checkbox (- [ ]) on that line."
        
        return f"Error: Task snippet '{task_snippet}' not found in plan."
    except Exception as e:
        return f"Error updating task: {str(e)}"

def read_project_file(filename: str):
    """Read any file in the project (generic read)."""
    try:
        target = BASE_DIR / filename
        # 简单的安全检查，防止读取系统文件
        if ".." in filename or filename.startswith("/"):
             return "Error: Invalid file path."
             
        if not target.exists():
            return "Error: File does not exist."
        return target.read_text(encoding='utf-8')
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_project_file(filename: str, content: str):
    """Write/Overwrite any file in the project (generic write)."""
    try:
        target = BASE_DIR / filename
        if ".." in filename or filename.startswith("/"):
             return "Error: Invalid file path."

        # Ensure parent dirs exist
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return f"Success: Wrote to {filename}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def run_shell_command(command: str):
    """
    Execute a shell command (e.g., run tests, list files).
    Restricted to non-interactive commands.
    """
    # Safety: Deny list
    forbidden = ["rm -rf", "mkfs", ":(){:|:&};:", "> /dev/sd", "dd if="]
    if any(bad in command for bad in forbidden):
        return "Error: Command blocked by safety policy."

    try:
        # Run command with timeout
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=30,
            cwd=str(BASE_DIR)
        )
        output = f"Exit Code: {result.returncode}\n"
        if result.stdout: output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr: output += f"STDERR:\n{result.stderr}\n"
        return output.strip()
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (30s limit)."
    except Exception as e:
        return f"Error executing command: {str(e)}"