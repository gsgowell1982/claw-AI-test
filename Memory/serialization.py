"""
Memory Serialization - 记忆序列化

负责:
- 数据序列化与反序列化
- 格式转换
- 压缩处理
"""

from typing import Optional, Dict, Any, Union
from dataclasses import dataclass
import json
import pickle
import base64
import zlib
from enum import Enum


class SerializationFormat(Enum):
    """序列化格式"""
    JSON = "json"
    PICKLE = "pickle"
    MSGPACK = "msgpack"


class CompressionType(Enum):
    """压缩类型"""
    NONE = "none"
    ZLIB = "zlib"
    GZIP = "gzip"
    LZ4 = "lz4"


@dataclass
class SerializedData:
    """序列化数据"""
    data: bytes
    format: SerializationFormat
    compression: CompressionType
    original_size: int
    compressed_size: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": base64.b64encode(self.data).decode('utf-8'),
            "format": self.format.value,
            "compression": self.compression.value,
            "original_size": self.original_size,
            "compressed_size": self.compressed_size
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SerializedData":
        return cls(
            data=base64.b64decode(data["data"]),
            format=SerializationFormat(data["format"]),
            compression=CompressionType(data["compression"]),
            original_size=data["original_size"],
            compressed_size=data["compressed_size"]
        )


class MemorySerializer:
    """
    记忆序列化器
    
    处理记忆数据的序列化和反序列化
    """
    
    def __init__(
        self,
        default_format: SerializationFormat = SerializationFormat.JSON,
        default_compression: CompressionType = CompressionType.NONE,
        compression_threshold: int = 1024
    ):
        self.default_format = default_format
        self.default_compression = default_compression
        self.compression_threshold = compression_threshold
    
    def serialize(
        self,
        data: Any,
        format: Optional[SerializationFormat] = None,
        compression: Optional[CompressionType] = None
    ) -> SerializedData:
        """
        序列化数据
        
        Args:
            data: 要序列化的数据
            format: 序列化格式
            compression: 压缩类型
            
        Returns:
            序列化数据
        """
        fmt = format or self.default_format
        comp = compression or self.default_compression
        
        # 序列化
        if fmt == SerializationFormat.JSON:
            serialized = self._serialize_json(data)
        elif fmt == SerializationFormat.PICKLE:
            serialized = self._serialize_pickle(data)
        else:
            serialized = self._serialize_json(data)
        
        original_size = len(serialized)
        
        # 压缩
        if comp != CompressionType.NONE or original_size > self.compression_threshold:
            if comp == CompressionType.NONE:
                comp = CompressionType.ZLIB
            compressed = self._compress(serialized, comp)
        else:
            compressed = serialized
        
        return SerializedData(
            data=compressed,
            format=fmt,
            compression=comp if compressed != serialized else CompressionType.NONE,
            original_size=original_size,
            compressed_size=len(compressed)
        )
    
    def deserialize(
        self,
        serialized: SerializedData
    ) -> Any:
        """
        反序列化数据
        
        Args:
            serialized: 序列化数据
            
        Returns:
            原始数据
        """
        # 解压
        if serialized.compression != CompressionType.NONE:
            data = self._decompress(serialized.data, serialized.compression)
        else:
            data = serialized.data
        
        # 反序列化
        if serialized.format == SerializationFormat.JSON:
            return self._deserialize_json(data)
        elif serialized.format == SerializationFormat.PICKLE:
            return self._deserialize_pickle(data)
        else:
            return self._deserialize_json(data)
    
    def _serialize_json(self, data: Any) -> bytes:
        """JSON 序列化"""
        return json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
    
    def _deserialize_json(self, data: bytes) -> Any:
        """JSON 反序列化"""
        return json.loads(data.decode('utf-8'))
    
    def _serialize_pickle(self, data: Any) -> bytes:
        """Pickle 序列化"""
        return pickle.dumps(data)
    
    def _deserialize_pickle(self, data: bytes) -> Any:
        """Pickle 反序列化"""
        return pickle.loads(data)
    
    def _compress(self, data: bytes, compression: CompressionType) -> bytes:
        """压缩数据"""
        if compression == CompressionType.ZLIB:
            return zlib.compress(data)
        elif compression == CompressionType.GZIP:
            import gzip
            return gzip.compress(data)
        else:
            return data
    
    def _decompress(self, data: bytes, compression: CompressionType) -> bytes:
        """解压数据"""
        if compression == CompressionType.ZLIB:
            return zlib.decompress(data)
        elif compression == CompressionType.GZIP:
            import gzip
            return gzip.decompress(data)
        else:
            return data
    
    def to_base64(self, data: Any) -> str:
        """转换为 Base64 字符串"""
        serialized = self.serialize(data)
        return base64.b64encode(serialized.data).decode('utf-8')
    
    def from_base64(
        self,
        data: str,
        format: SerializationFormat = SerializationFormat.JSON
    ) -> Any:
        """从 Base64 字符串恢复"""
        decoded = base64.b64decode(data)
        
        serialized = SerializedData(
            data=decoded,
            format=format,
            compression=CompressionType.NONE,
            original_size=len(decoded),
            compressed_size=len(decoded)
        )
        
        return self.deserialize(serialized)
    
    def get_compression_ratio(self, serialized: SerializedData) -> float:
        """获取压缩比"""
        if serialized.original_size == 0:
            return 0.0
        return 1 - (serialized.compressed_size / serialized.original_size)


# 全局序列化器
_default_serializer: Optional[MemorySerializer] = None


def get_serializer() -> MemorySerializer:
    """获取全局序列化器"""
    global _default_serializer
    if _default_serializer is None:
        _default_serializer = MemorySerializer()
    return _default_serializer
