import docker
import tarfile
import io
import json
import asyncio
from typing import Dict
from .base import ICodeSandbox

class DockerSandboxAdapter(ICodeSandbox):
    """
    基于 Docker 的安全代码执行环境
    前提：宿主机安装了 Docker，且有构建好的 python-runner 镜像
    """
    def __init__(self, image: str = "opencoze/python-runner:latest"):
        self.client = docker.from_env()
        self.image = image

    async def run_code(self, code: str, inputs: Dict, timeout: int = 30) -> Dict:
        # 1. 准备代码包装器 (将 inputs 作为 JSON 传入，捕获 stdout/stderr)
        wrapped_code = f"""
import sys
import json
import asyncio
{code}

# 注入 inputs
inputs = json.loads('{json.dumps(inputs)}')

# 模拟 Coze Args
class Args:
    def __init__(self, p): self.params = p
    def get(self, k, d=None): return self.params.get(k, d)

# 执行
try:
    if 'main' in locals():
        res = asyncio.run(main(Args(inputs)))
        print(json.dumps(res)) # 输出到 stdout
    else:
        print(json.dumps({{"error": "No main function"}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
        
        loop = asyncio.get_event_loop()
        
        def _docker_run():
            try:
                # 启动临时容器
                container = self.client.containers.run(
                    self.image,
                    command=f"python -c \"{wrapped_code.replace('"', '\\"')}\"", # 简化处理，实际应写入文件挂载
                    mem_limit="128m",
                    cpu_period=100000,
                    cpu_quota=50000, # 0.5 CPU
                    network_disabled=True, # 禁止联网 (除非是插件调用)
                    detach=True
                )
                
                try:
                    # 等待执行
                    result = container.wait(timeout=timeout)
                    logs = container.logs().decode("utf-8")
                    
                    if result['StatusCode'] != 0:
                        return {"error": f"Runtime Error: {logs}"}
                    
                    # 解析 JSON 输出
                    try:
                        return json.loads(logs.strip())
                    except:
                        return {"output": logs}
                        
                finally:
                    container.remove(force=True)
            except Exception as e:
                return {"error": str(e)}

        # 在线程池中运行 Docker 阻塞操作
        return await loop.run_in_executor(None, _docker_run)