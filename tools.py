import time
import datetime
import random

# ================= 全局工具 =================

def get_current_time():
    """获取当前的系统时间"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ================= 服务器运维工具 (Server Ops) =================

def ping_server(hostname: str):
    """
    检查服务器的网络连通性。
    """
    # 模拟网络操作
    time.sleep(0.5) 
    latency = random.randint(10, 100)
    if random.random() < 0.1: # 10% 概率丢包
        return f"Request timed out for {hostname}."
    return f"Reply from {hostname}: bytes=32 time={latency}ms TTL=54"

def restart_service(hostname: str, service_name: str = "nginx"):
    """
    [敏感操作] 重启指定服务器上的服务。
    这个工具在 yaml 中配置为 sensitive: true，因此会被 HITL 拦截。
    """
    # 只有经过人工审批后，Agent 才会真正执行到这里
    print(f"\n[SYSTEM LOG] 正在执行重启操作: Host={hostname}, Service={service_name} ...")
    time.sleep(1)
    return f"Service '{service_name}' on {hostname} restarted successfully. Uptime: 0s."

# ================= 数据迁移工具 (Data Migration) =================

def export_data(source_db: str):
    """从源数据库导出数据"""
    return f"Data exported from {source_db} to /tmp/dump.sql (Size: 500MB)"

def import_data(target_db: str, file_path: str = "/tmp/dump.sql"):
    """
    [敏感操作] 将数据导入目标数据库。
    会被 HITL 拦截。
    """
    print(f"\n[SYSTEM LOG] 正在向 {target_db} 导入数据 ...")
    time.sleep(1)
    return f"Data import to {target_db} completed. Rows affected: 1,000,000."

def verify_integrity(source_db: str, target_db: str):
    """校验数据一致性"""
    return f"Integrity check passed: {source_db} == {target_db} (Hash match)."