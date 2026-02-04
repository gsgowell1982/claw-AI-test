"""
Tool Metadata - 成本与频率统计

负责:
- 工具使用统计
- 成本计算
- 频率分析
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import threading


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    cost_per_call: float = 0.0
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0
    tags: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "cost_per_call": self.cost_per_call,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate": self.success_rate,
            "tags": self.tags,
            "custom_fields": self.custom_fields
        }


@dataclass
class UsageRecord:
    """使用记录"""
    tool_name: str
    timestamp: datetime
    duration_ms: float
    success: bool
    cost: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetadataCollector:
    """
    元数据收集器
    
    收集和分析工具使用数据
    """
    
    def __init__(self, retention_days: int = 30):
        self.retention_days = retention_days
        
        self._metadata: Dict[str, ToolMetadata] = {}
        self._usage_records: List[UsageRecord] = []
        self._aggregated_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_calls": 0,
            "successful_calls": 0,
            "total_duration_ms": 0,
            "total_cost": 0,
            "last_used": None
        })
        self._lock = threading.Lock()
    
    def set_metadata(self, metadata: ToolMetadata) -> None:
        """设置工具元数据"""
        self._metadata[metadata.name] = metadata
    
    def get_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        return self._metadata.get(tool_name)
    
    def record_usage(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool,
        cost: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        记录使用情况
        
        Args:
            tool_name: 工具名称
            duration_ms: 执行时长(毫秒)
            success: 是否成功
            cost: 成本
            metadata: 额外元数据
        """
        # 获取成本
        if cost is None:
            tool_meta = self._metadata.get(tool_name)
            cost = tool_meta.cost_per_call if tool_meta else 0.0
        
        record = UsageRecord(
            tool_name=tool_name,
            timestamp=datetime.now(),
            duration_ms=duration_ms,
            success=success,
            cost=cost,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._usage_records.append(record)
            
            # 更新聚合统计
            stats = self._aggregated_stats[tool_name]
            stats["total_calls"] += 1
            if success:
                stats["successful_calls"] += 1
            stats["total_duration_ms"] += duration_ms
            stats["total_cost"] += cost
            stats["last_used"] = record.timestamp.isoformat()
            
            # 清理过期记录
            self._cleanup_old_records()
    
    def _cleanup_old_records(self) -> None:
        """清理过期记录"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        self._usage_records = [
            r for r in self._usage_records
            if r.timestamp > cutoff
        ]
    
    def get_stats(self, tool_name: str) -> Dict[str, Any]:
        """
        获取工具统计
        
        Args:
            tool_name: 工具名称
            
        Returns:
            统计数据
        """
        stats = self._aggregated_stats.get(tool_name, {})
        
        total_calls = stats.get("total_calls", 0)
        successful_calls = stats.get("successful_calls", 0)
        total_duration = stats.get("total_duration_ms", 0)
        
        return {
            "tool_name": tool_name,
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": total_calls - successful_calls,
            "success_rate": successful_calls / total_calls if total_calls > 0 else 0,
            "avg_duration_ms": total_duration / total_calls if total_calls > 0 else 0,
            "total_cost": stats.get("total_cost", 0),
            "last_used": stats.get("last_used")
        }
    
    def get_all_stats(self) -> List[Dict[str, Any]]:
        """获取所有工具统计"""
        return [
            self.get_stats(tool_name)
            for tool_name in self._aggregated_stats.keys()
        ]
    
    def get_usage_history(
        self,
        tool_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取使用历史
        
        Args:
            tool_name: 工具名称过滤
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制
            
        Returns:
            使用记录列表
        """
        records = self._usage_records
        
        if tool_name:
            records = [r for r in records if r.tool_name == tool_name]
        
        if start_time:
            records = [r for r in records if r.timestamp >= start_time]
        
        if end_time:
            records = [r for r in records if r.timestamp <= end_time]
        
        return [
            {
                "tool_name": r.tool_name,
                "timestamp": r.timestamp.isoformat(),
                "duration_ms": r.duration_ms,
                "success": r.success,
                "cost": r.cost,
                "metadata": r.metadata
            }
            for r in records[-limit:]
        ]
    
    def get_cost_summary(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        获取成本摘要
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            成本摘要
        """
        records = self._usage_records
        
        if start_time:
            records = [r for r in records if r.timestamp >= start_time]
        
        if end_time:
            records = [r for r in records if r.timestamp <= end_time]
        
        total_cost = sum(r.cost for r in records)
        cost_by_tool = defaultdict(float)
        
        for record in records:
            cost_by_tool[record.tool_name] += record.cost
        
        return {
            "total_cost": total_cost,
            "cost_by_tool": dict(cost_by_tool),
            "record_count": len(records),
            "period": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None
            }
        }
    
    def get_frequency_analysis(
        self,
        interval: str = "hour"
    ) -> Dict[str, Any]:
        """
        获取频率分析
        
        Args:
            interval: 时间间隔 ('hour', 'day', 'week')
            
        Returns:
            频率分析结果
        """
        from collections import Counter
        
        def get_bucket(timestamp: datetime) -> str:
            if interval == "hour":
                return timestamp.strftime("%Y-%m-%d %H:00")
            elif interval == "day":
                return timestamp.strftime("%Y-%m-%d")
            elif interval == "week":
                return timestamp.strftime("%Y-W%W")
            return timestamp.isoformat()
        
        buckets = Counter()
        tool_buckets = defaultdict(Counter)
        
        for record in self._usage_records:
            bucket = get_bucket(record.timestamp)
            buckets[bucket] += 1
            tool_buckets[record.tool_name][bucket] += 1
        
        return {
            "interval": interval,
            "total_by_period": dict(buckets),
            "by_tool": {
                tool: dict(counter)
                for tool, counter in tool_buckets.items()
            }
        }
    
    def clear_stats(self) -> None:
        """清空统计"""
        with self._lock:
            self._usage_records.clear()
            self._aggregated_stats.clear()


# 全局收集器
_default_collector: Optional[MetadataCollector] = None


def get_collector() -> MetadataCollector:
    """获取全局收集器"""
    global _default_collector
    if _default_collector is None:
        _default_collector = MetadataCollector()
    return _default_collector
