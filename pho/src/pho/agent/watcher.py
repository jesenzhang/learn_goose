import time
import logging
import asyncio
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class ConfigFileHandler(FileSystemEventHandler):
    """处理文件修改事件，带防抖动逻辑"""
    def __init__(self, config_path: str, callback: Callable, loop: asyncio.AbstractEventLoop):
        self.config_path = config_path
        self.callback = callback
        self.loop = loop
        self._last_trigger = 0
        self._debounce_seconds = 1.0  # 防抖时间

    def on_modified(self, event):
        if event.is_directory:
            return
            
        # 检查是否是我们关心的那个配置文件
        if event.src_path.endswith(self.config_path) or self.config_path in event.src_path:
            current_time = time.time()
            if current_time - self._last_trigger > self._debounce_seconds:
                self._last_trigger = current_time
                logger.info(f"⚡ Configuration change detected: {event.src_path}")
                
                # 关键：将重载任务调度回主事件循环，保证线程安全
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self.callback())
                    )

class ConfigWatcher:
    """配置监听器管理器"""
    def __init__(self, config_path: str, reload_callback: Callable):
        self.observer = Observer()
        self.config_path = config_path
        # 获取当前的 asyncio loop，以便回调切回主线程
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            
        self.handler = ConfigFileHandler(config_path, reload_callback, self.loop)

    def start(self):
        # 监听配置文件所在的目录
        import os
        directory = os.path.dirname(os.path.abspath(self.config_path))
        self.observer.schedule(self.handler, directory, recursive=False)
        self.observer.start()
        logger.info(f"👀 Watching for config changes in: {self.config_path}")

    def stop(self):
        self.observer.stop()
        self.observer.join()