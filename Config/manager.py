"""
Config Manager - 配置管理器

负责:
- 环境变量管理
- 网络地址配置
- 配置验证
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path
import os
import json


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    workers: int = 1
    reload: bool = False


@dataclass
class OllamaConfig:
    """Ollama 配置"""
    host: str = "http://localhost:11434"
    model: str = "qwen2.5-vl:32b"
    timeout: int = 300


@dataclass
class MemoryConfig:
    """内存配置"""
    short_term_ttl: int = 3600
    short_term_max_items: int = 10000
    long_term_storage_path: str = "./data/long_term.json"
    vector_dimension: int = 768


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


@dataclass
class SecurityConfig:
    """安全配置"""
    enable_auth: bool = False
    secret_key: str = ""
    token_expire_minutes: int = 60
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])


@dataclass
class AppConfig:
    """应用配置"""
    name: str = "OpenClaw"
    version: str = "1.0.0"
    environment: str = "development"
    server: ServerConfig = field(default_factory=ServerConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


class ConfigManager:
    """
    配置管理器
    
    集中管理所有应用配置
    """
    
    ENV_PREFIX = "OPENCLAW_"
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else None
        self._config = AppConfig()
        self._custom: Dict[str, Any] = {}
        
        # 加载配置
        self._load_config()
        self._load_from_env()
    
    def _load_config(self) -> None:
        """从文件加载配置"""
        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._apply_config(data)
            except Exception:
                pass
    
    def _apply_config(self, data: Dict[str, Any]) -> None:
        """应用配置数据"""
        if "server" in data:
            for key, value in data["server"].items():
                if hasattr(self._config.server, key):
                    setattr(self._config.server, key, value)
        
        if "ollama" in data:
            for key, value in data["ollama"].items():
                if hasattr(self._config.ollama, key):
                    setattr(self._config.ollama, key, value)
        
        if "memory" in data:
            for key, value in data["memory"].items():
                if hasattr(self._config.memory, key):
                    setattr(self._config.memory, key, value)
        
        if "logging" in data:
            for key, value in data["logging"].items():
                if hasattr(self._config.logging, key):
                    setattr(self._config.logging, key, value)
        
        if "security" in data:
            for key, value in data["security"].items():
                if hasattr(self._config.security, key):
                    setattr(self._config.security, key, value)
        
        if "name" in data:
            self._config.name = data["name"]
        
        if "environment" in data:
            self._config.environment = data["environment"]
    
    def _load_from_env(self) -> None:
        """从环境变量加载配置"""
        # 服务器配置
        self._config.server.host = os.getenv(
            f"{self.ENV_PREFIX}HOST",
            self._config.server.host
        )
        self._config.server.port = int(os.getenv(
            f"{self.ENV_PREFIX}PORT",
            str(self._config.server.port)
        ))
        self._config.server.debug = os.getenv(
            f"{self.ENV_PREFIX}DEBUG",
            str(self._config.server.debug)
        ).lower() == "true"
        
        # Ollama 配置
        self._config.ollama.host = os.getenv(
            f"{self.ENV_PREFIX}OLLAMA_HOST",
            self._config.ollama.host
        )
        self._config.ollama.model = os.getenv(
            f"{self.ENV_PREFIX}OLLAMA_MODEL",
            self._config.ollama.model
        )
        
        # 环境
        self._config.environment = os.getenv(
            f"{self.ENV_PREFIX}ENV",
            self._config.environment
        )
        
        # 安全配置
        self._config.security.secret_key = os.getenv(
            f"{self.ENV_PREFIX}SECRET_KEY",
            self._config.security.secret_key
        )
    
    @property
    def config(self) -> AppConfig:
        """获取配置"""
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键 (支持点号分隔,如 'server.port')
            default: 默认值
            
        Returns:
            配置值
        """
        parts = key.split(".")
        
        # 检查自定义配置
        if key in self._custom:
            return self._custom[key]
        
        # 遍历配置树
        obj = self._config
        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return default
        
        return obj
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 值
        """
        self._custom[key] = value
    
    def get_server_url(self) -> str:
        """获取服务器 URL"""
        host = self._config.server.host
        if host == "0.0.0.0":
            host = "localhost"
        return f"http://{host}:{self._config.server.port}"
    
    def get_ollama_url(self) -> str:
        """获取 Ollama URL"""
        return self._config.ollama.host
    
    def is_development(self) -> bool:
        """是否为开发环境"""
        return self._config.environment == "development"
    
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self._config.environment == "production"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self._config.name,
            "version": self._config.version,
            "environment": self._config.environment,
            "server": {
                "host": self._config.server.host,
                "port": self._config.server.port,
                "debug": self._config.server.debug,
                "workers": self._config.server.workers
            },
            "ollama": {
                "host": self._config.ollama.host,
                "model": self._config.ollama.model,
                "timeout": self._config.ollama.timeout
            },
            "memory": {
                "short_term_ttl": self._config.memory.short_term_ttl,
                "short_term_max_items": self._config.memory.short_term_max_items,
                "vector_dimension": self._config.memory.vector_dimension
            },
            "logging": {
                "level": self._config.logging.level
            }
        }
    
    def save(self, path: Optional[str] = None) -> bool:
        """
        保存配置到文件
        
        Args:
            path: 文件路径
            
        Returns:
            是否成功
        """
        save_path = Path(path) if path else self.config_path
        
        if not save_path:
            return False
        
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            
            return True
        except Exception:
            return False


# 全局配置实例
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """获取全局配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def init_config(config_path: Optional[str] = None) -> ConfigManager:
    """初始化配置管理器"""
    global _config_manager
    _config_manager = ConfigManager(config_path)
    return _config_manager
