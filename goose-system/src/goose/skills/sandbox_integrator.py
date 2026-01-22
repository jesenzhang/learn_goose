"""
Sandbox Integrator - 沙箱集成器

功能:
- 将技能目录挂载到沙箱
- 执行脚本并捕获输出
- 处理生成的文件

Reference: Agent Skills 架构设计手册 - 隔离沙箱基础设施
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import tempfile
import shutil
import os
import subprocess
import sys
import time
from datetime import datetime


class ExecutionResult:
    """执行结果"""
    
    def __init__(
        self,
        success: bool,
        stdout: str = "",
        stderr: str = "",
        return_code: int = -1,
        output_files: Optional[Dict[str, str]] = None,
        execution_time: float = 0.0,
        error: Optional[str] = None
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        self.output_files = output_files or {}
        self.execution_time = execution_time
        self.error = error
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "output_files": self.output_files,
            "execution_time": self.execution_time,
            "error": self.error,
            "timestamp": self.timestamp,
        }
    
    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return f"ExecutionResult({status}, time={self.execution_time:.2f}s)"


class SandboxIntegrator:
    """
    沙箱集成器
    
    功能:
    1. 将技能目录挂载到沙箱工作目录
    2. 执行脚本并捕获输出
    3. 处理生成的文件
    
    注意: 当前实现使用简单的目录操作,
    生产环境应该集成 Docker、gVisor 或 Firecracker
    """
    
    def __init__(
        self,
        output_dir: Optional[Path] = None,
        timeout: int = 30,
        memory_limit_mb: int = 256
    ):
        """
        初始化沙箱集成器
        
        Args:
            output_dir: 输出目录 (默认临时目录)
            timeout: 执行超时 (秒)
            memory_limit_mb: 内存限制 (MB)
        """
        self.base_output_dir = output_dir or Path(tempfile.gettempdir()) / "skill_outputs"
        self.base_output_dir.mkdir(exist_ok=True)
        self.timeout = timeout
        self.memory_limit_mb = memory_limit_mb
    
    @property
    def output_dir(self) -> Path:
        """获取输出目录"""
        return self.base_output_dir
    
    def mount_skill(self, skill_dir: Path) -> Path:
        """
        将技能目录挂载到沙箱工作目录
        
        使用符号链接或复制方式挂载
        
        Args:
            skill_dir: 技能目录
            
        Returns:
            挂载点路径
        """
        mount_point = self.base_output_dir / f"sandbox_{skill_dir.name}_{os.getpid()}"
        
        # 清理已存在的挂载点
        if mount_point.exists():
            shutil.rmtree(mount_point)
        
        # 复制技能目录
        try:
            shutil.copytree(skill_dir, mount_point)
        except Exception:
            # 如果复制失败，使用符号链接
            if mount_point.is_symlink() or mount_point.exists():
                mount_point.unlink()
            try:
                mount_point.symlink_to(skill_dir, target_is_directory=True)
            except Exception:
                # 最后尝试：创建目录并复制内容
                mount_point.mkdir(exist_ok=True)
                for item in skill_dir.iterdir():
                    src = skill_dir / item.name
                    dst = mount_point / item.name
                    if src.is_dir():
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
        
        return mount_point
    
    def unmount_skill(self, mount_point: Path) -> bool:
        """
        卸载技能目录
        
        Args:
            mount_point: 挂载点路径
            
        Returns:
            是否成功卸载
        """
        try:
            if mount_point.is_symlink():
                mount_point.unlink()
            elif mount_point.exists() and mount_point.is_dir():
                # 不删除原始技能目录，只清理挂载点
                for item in mount_point.iterdir():
                    dst = mount_point / item.name
                    # 如果是复制的文件，保留原始目录结构
            return True
        except Exception:
            pass
        return False
    
    def execute_script(
        self,
        script_path: Path,
        args: Optional[List[str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        working_dir: Optional[Path] = None
    ) -> ExecutionResult:
        """
        执行脚本
        
        Args:
            script_path: 脚本路径 (挂载后的路径)
            args: 脚本参数
            env_vars: 环境变量
            working_dir: 工作目录
            
        Returns:
            ExecutionResult: 执行结果
        """
        import time
        start_time = time.time()
        
        if not script_path.exists():
            return ExecutionResult(
                success=False,
                error=f"Script not found: {script_path}",
                execution_time=time.time() - start_time
            )
        
        if not script_path.is_file():
            return ExecutionResult(
                success=False,
                error=f"Not a file: {script_path}",
                execution_time=time.time() - start_time
            )
        
        # 检查脚本扩展名
        suffix = script_path.suffix.lower()
        if suffix == ".py":
            return self._execute_python(
                script_path, args, env_vars, working_dir, start_time
            )
        elif suffix in {".js", ".ts"}:
            return self._execute_node(
                script_path, args, env_vars, working_dir, start_time
            )
        else:
            return self._execute_shell(
                script_path, args, env_vars, working_dir, start_time
            )
    
    def _execute_python(
        self,
        script_path: Path,
        args: Optional[List[str]],
        env_vars: Optional[Dict[str, str]],
        working_dir: Optional[Path],
        start_time: float
    ) -> ExecutionResult:
        """执行 Python 脚本"""
        cmd = [sys.executable, str(script_path)] + (args or [])
        
        return self._run_command(
            cmd, env_vars, working_dir, start_time
        )
    
    def _execute_node(
        self,
        script_path: Path,
        args: Optional[List[str]],
        env_vars: Optional[Dict[str, str]],
        working_dir: Optional[Path],
        start_time: float
    ) -> ExecutionResult:
        """执行 Node.js 脚本"""
        import shutil
        
        if not shutil.which("node"):
            return ExecutionResult(
                success=False,
                error="Node.js not installed",
                execution_time=time.time() - start_time
            )
        
        cmd = ["node", str(script_path)] + (args or [])
        
        return self._run_command(
            cmd, env_vars, working_dir, start_time
        )
    
    def _execute_shell(
        self,
        script_path: Path,
        args: Optional[List[str]],
        env_vars: Optional[Dict[str, str]],
        working_dir: Optional[Path],
        start_time: float
    ) -> ExecutionResult:
        """执行 Shell 脚本"""
        cmd = ["bash", str(script_path)] + (args or [])
        
        return self._run_command(
            cmd, env_vars, working_dir, start_time
        )
    
    def _run_command(
        self,
        cmd: List[str],
        env_vars: Optional[Dict[str, str]],
        working_dir: Optional[Path],
        start_time: float
    ) -> ExecutionResult:
        """执行命令并捕获结果"""
        import subprocess
        import time
        
        try:
            # 准备环境变量
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)
            
            # 设置工作目录
            cwd = working_dir or self.base_output_dir
            
            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(cwd),
                timeout=self.timeout
            )
            
            execution_time = time.time() - start_time
            
            # 处理输出文件
            output_files = self._collect_output_files(cwd)
            
            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                output_files=output_files,
                execution_time=execution_time
            )
            
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error=f"Execution timed out ({self.timeout}s)",
                execution_time=time.time() - start_time
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    def _collect_output_files(self, directory: Path) -> Dict[str, str]:
        """
        收集输出文件
        
        将输出文件转换为 file:// 路径
        
        Args:
            directory: 目录路径
            
        Returns:
            {文件名: file://路径}
        """
        output_files = {}
        
        if not directory.exists():
            return output_files
        
        # 常见输出文件类型
        output_extensions = {
            ".pdf", ".xlsx", ".xls", ".csv", ".json",
            ".txt", ".md", ".html", ".xml", ".png",
            ".jpg", ".jpeg", ".gif"
        }
        
        try:
            for f in directory.rglob("*"):
                if f.is_file() and f.suffix.lower() in output_extensions:
                    try:
                        rel_path = f.relative_to(directory)
                        output_files[str(rel_path)] = f"file://{f}"
                    except ValueError:
                        output_files[f.name] = f"file://{f}"
        except Exception:
            pass
        
        return output_files
    
    def handle_output_files(
        self,
        mount_point: Path,
        output_patterns: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        处理生成的文件
        
        Args:
            mount_point: 挂载点
            output_patterns: 输出文件模式
            
        Returns:
            {文件名: 访问路径}
        """
        return self._collect_output_files(mount_point)
    
    def cleanup_output_dir(self, max_age_hours: int = 24) -> int:
        """
        清理旧的输出文件
        
        Args:
            max_age_hours: 最大保留时间 (小时)
            
        Returns:
            清理的文件数量
        """
        import time
        
        cleaned_count = 0
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        if not self.base_output_dir.exists():
            return 0
        
        try:
            for item in self.base_output_dir.iterdir():
                if item.is_dir():
                    # 检查目录修改时间
                    mtime = item.stat().st_mtime
                    if mtime < cutoff_time:
                        shutil.rmtree(item)
                        cleaned_count += 1
        except Exception:
            pass
        
        return cleaned_count
    
    def get_sandbox_info(self) -> Dict[str, Any]:
        """获取沙箱信息"""
        return {
            "output_dir": str(self.base_output_dir),
            "timeout": self.timeout,
            "memory_limit_mb": self.memory_limit_mb,
            "exists": self.base_output_dir.exists(),
        }


class SandboxConfig:
    """
    沙箱配置
    
    用于配置沙箱的行为
    """
    
    def __init__(
        self,
        enable_network: bool = False,
        enable_file_write: bool = True,
        allowed_dirs: Optional[List[str]] = None,
        blocked_cmds: Optional[List[str]] = None
    ):
        """
        初始化沙箱配置
        
        Args:
            enable_network: 是否允许网络访问
            enable_file_write: 是否允许写文件
            allowed_dirs: 允许访问的目录列表
            blocked_cmds: 禁止执行的命令列表
        """
        self.enable_network = enable_network
        self.enable_file_write = enable_file_write
        self.allowed_dirs = allowed_dirs or ["/tmp", "/var/tmp"]
        self.blocked_cmds = blocked_cmds or [
            "rm", "dd", "mkfs", "chmod", "chown",
            "wget", "curl", "nc", "netcat"
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enable_network": self.enable_network,
            "enable_file_write": self.enable_file_write,
            "allowed_dirs": self.allowed_dirs,
            "blocked_cmds": self.blocked_cmds,
        }
