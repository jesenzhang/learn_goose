"""
Experiment Management

实验特性管理，支持：
- 实验特性注册
- 实验启用/禁用
- 持久化存储

Reference: goose-rs/crates/goose/src/config/experiments.rs
"""

import os
import yaml
import threading
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

logger = logging.getLogger("goose.config.experiments")


class ExperimentState(str, Enum):
    """实验状态"""
    DRAFT = "draft"
    ENABLED = "enabled"
    DISABLED = "disabled"
    CONTROL = "control"


@dataclass
class Experiment:
    """实验配置"""
    name: str
    description: str = ""
    default_enabled: bool = False
    state: ExperimentState = ExperimentState.DRAFT
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "default_enabled": self.default_enabled,
            "state": self.state.value,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Experiment':
        """从字典创建"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            default_enabled=data.get("default_enabled", False),
            state=ExperimentState(data.get("state", "draft")),
            metadata=data.get("metadata", {}),
        )


class ExperimentManager:
    """实验特性管理器"""
    
    EXPERIMENTS_FILE = "experiments.yaml"
    
    _instance: Optional['ExperimentManager'] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'ExperimentManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = ExperimentManager()
        return cls._instance
    
    @classmethod
    def set_instance(cls, instance: 'ExperimentManager'):
        with cls._lock:
            cls._instance = instance
    
    def __init__(self, config_dir: Optional[str] = None):
        self._config_dir = config_dir or os.path.expanduser("~/.config/goose")
        self._experiments_file = Path(self._config_dir) / self.EXPERIMENTS_FILE
        self._experiments: Dict[str, Experiment] = {}
        self._lock = threading.Lock()
        self._register_default_experiments()
        self._load_experiments()
    
    def _register_default_experiments(self) -> None:
        """注册默认实验"""
        pass
    
    def register_experiment(
        self,
        name: str,
        description: str = "",
        default_enabled: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Experiment:
        """注册实验"""
        with self._lock:
            if name not in self._experiments:
                self._experiments[name] = Experiment(
                    name=name,
                    description=description,
                    default_enabled=default_enabled,
                    state=ExperimentState.ENABLED if default_enabled else ExperimentState.DRAFT,
                    metadata=metadata or {},
                )
            return self._experiments[name]
    
    def _load_experiments(self) -> None:
        """加载实验配置"""
        if self._experiments_file.exists():
            try:
                with open(self._experiments_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                
                for exp_data in data.get("experiments", []):
                    if isinstance(exp_data, dict):
                        exp = Experiment.from_dict(exp_data)
                        self._experiments[exp.name] = exp
            except Exception as e:
                logger.error(f"Failed to load experiments: {e}")
    
    def _save_experiments(self) -> None:
        """保存实验配置"""
        try:
            self._experiments_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "experiments": [
                    exp.to_dict() for exp in self._experiments.values()
                ]
            }
            
            with open(self._experiments_file, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"Saved experiments to {self._experiments_file}")
        except Exception as e:
            logger.error(f"Failed to save experiments: {e}")
    
    def get_all(self) -> List[tuple]:
        """获取所有实验"""
        with self._lock:
            return [
                (name, exp.state == ExperimentState.ENABLED)
                for name, exp in self._experiments.items()
            ]
    
    def get(self, name: str) -> Optional[Experiment]:
        """获取实验"""
        with self._lock:
            return self._experiments.get(name)
    
    def is_enabled(self, name: str) -> bool:
        """检查实验是否启用"""
        exp = self.get(name)
        if exp:
            return exp.state == ExperimentState.ENABLED
        return False
    
    def set_enabled(self, name: str, enabled: bool) -> bool:
        """设置实验启用状态"""
        with self._lock:
            if name in self._experiments:
                self._experiments[name].state = (
                    ExperimentState.ENABLED if enabled else ExperimentState.DISABLED
                )
                self._save_experiments()
                return True
            return False
    
    def enable(self, name: str) -> bool:
        """启用实验"""
        return self.set_enabled(name, True)
    
    def disable(self, name: str) -> bool:
        """禁用实验"""
        return self.set_enabled(name, False)
    
    def reset(self, name: str) -> bool:
        """重置实验为默认状态"""
        with self._lock:
            if name in self._experiments:
                exp = self._experiments[name]
                exp.state = ExperimentState.ENABLED if exp.default_enabled else ExperimentState.DRAFT
                self._save_experiments()
                return True
            return False
    
    def remove(self, name: str) -> bool:
        """删除实验"""
        with self._lock:
            if name in self._experiments:
                del self._experiments[name]
                self._save_experiments()
                return True
            return False


# 全局快捷函数

def get_experiment_manager() -> ExperimentManager:
    """获取实验管理器单例"""
    return ExperimentManager.get_instance()


def get_all_experiments() -> List[tuple]:
    """获取所有实验"""
    return get_experiment_manager().get_all()


def is_experiment_enabled(name: str) -> bool:
    """检查实验是否启用"""
    return get_experiment_manager().is_enabled(name)


def set_experiment_enabled(name: str, enabled: bool) -> bool:
    """设置实验启用状态"""
    return get_experiment_manager().set_enabled(name, enabled)


def enable_experiment(name: str) -> bool:
    """启用实验"""
    return get_experiment_manager().enable(name)


def disable_experiment(name: str) -> bool:
    """禁用实验"""
    return get_experiment_manager().disable(name)


def reset_experiment(name: str) -> bool:
    """重置实验"""
    return get_experiment_manager().reset(name)


def register_experiment(
    name: str,
    description: str = "",
    default_enabled: bool = False,
    metadata: Optional[Dict[str, Any]] = None
) -> Experiment:
    """注册实验"""
    return get_experiment_manager().register_experiment(
        name, description, default_enabled, metadata
    )
