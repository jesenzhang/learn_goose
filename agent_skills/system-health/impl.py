import platform
import shutil

def get_os_info():
    """
    Returns basic operating system information.
    """
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor()
    }

def get_disk_usage(path: str = "."):
    """
    Returns disk usage statistics for the given path.
    """
    total, used, free = shutil.disk_usage(path)
    return {
        "total_gb": round(total / (2**30), 2),
        "used_gb": round(used / (2**30), 2),
        "free_gb": round(free / (2**30), 2)
    }