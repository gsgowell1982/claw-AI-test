"""
Chat Logger - 聊天交互日志记录器

负责:
- 记录所有聊天交互
- 保存到 Test 目录
- 格式化日志输出
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import threading


class ChatLogger:
    """
    聊天日志记录器
    
    将聊天交互记录到文件
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path(__file__).parent
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "chat_interactions.log"
        self.json_file = self.log_dir / "chat_interactions.json"
        self._lock = threading.Lock()
        self._interactions = []
        
        # 加载已有数据
        self._load_existing()
    
    def _load_existing(self):
        """加载已有的交互记录"""
        if self.json_file.exists():
            try:
                with open(self.json_file, 'r', encoding='utf-8') as f:
                    self._interactions = json.load(f)
            except:
                self._interactions = []
    
    def log_interaction(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        duration_ms: float = 0,
        chunks: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        记录一次交互
        
        Args:
            session_id: 会话ID
            user_message: 用户消息
            assistant_response: 助手回复
            duration_ms: 响应时长(毫秒)
            chunks: 流式块数量
            metadata: 额外元数据
        """
        timestamp = datetime.now()
        
        interaction = {
            "timestamp": timestamp.isoformat(),
            "session_id": session_id,
            "user_message": user_message,
            "assistant_response": assistant_response,
            "duration_ms": duration_ms,
            "chunks": chunks,
            "metadata": metadata or {}
        }
        
        with self._lock:
            self._interactions.append(interaction)
            
            # 写入文本日志
            self._write_text_log(interaction, timestamp)
            
            # 写入 JSON 日志
            self._write_json_log()
    
    def _write_text_log(self, interaction: Dict, timestamp: datetime):
        """写入文本格式日志"""
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"时间: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"会话: {interaction['session_id'][:8]}...\n")
            f.write(f"耗时: {interaction['duration_ms']:.0f}ms | Chunks: {interaction['chunks']}\n")
            f.write("-" * 60 + "\n")
            f.write(f"用户: {interaction['user_message']}\n")
            f.write("-" * 60 + "\n")
            f.write(f"助手: {interaction['assistant_response']}\n")
            f.write("=" * 60 + "\n\n")
    
    def _write_json_log(self):
        """写入 JSON 格式日志"""
        with open(self.json_file, 'w', encoding='utf-8') as f:
            json.dump(self._interactions, f, ensure_ascii=False, indent=2)
    
    def get_recent(self, limit: int = 10):
        """获取最近的交互记录"""
        return self._interactions[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._interactions:
            return {"total": 0}
        
        total_duration = sum(i.get("duration_ms", 0) for i in self._interactions)
        avg_duration = total_duration / len(self._interactions) if self._interactions else 0
        
        return {
            "total_interactions": len(self._interactions),
            "total_duration_ms": total_duration,
            "avg_duration_ms": avg_duration,
            "log_file": str(self.log_file),
            "json_file": str(self.json_file)
        }


# 全局实例
_chat_logger: Optional[ChatLogger] = None


def get_chat_logger() -> ChatLogger:
    """获取全局聊天日志记录器"""
    global _chat_logger
    if _chat_logger is None:
        _chat_logger = ChatLogger()
    return _chat_logger


def log_chat(
    session_id: str,
    user_message: str,
    assistant_response: str,
    **kwargs
):
    """便捷的日志记录函数"""
    get_chat_logger().log_interaction(
        session_id=session_id,
        user_message=user_message,
        assistant_response=assistant_response,
        **kwargs
    )
