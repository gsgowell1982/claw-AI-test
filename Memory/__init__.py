# Memory Layer - 记忆层 v2.5.3
"""
Memory 层负责:
- 短期记忆管理（会话内缓存）
- 长期记忆存储（SQLite 持久化）
- 语义级记忆检索（Embedding）
- 错误分析与学习
- 智能代码截断

v2.5.3 更新:
- 新增 embeddings 模块：向量嵌入和语义搜索
- 新增 code_utils 模块：智能代码截断
- 长期记忆支持语义检索
- 执行历史自动清理
"""

from .short_term import (
    ShortTermMemory,
    get_session_memory,
    clear_session_memory
)
from .long_term import (
    LongTermMemory,
    get_long_term_memory,
    LearnedExperience
)
from .error_analyzer import (
    ErrorAnalyzer,
    ErrorAnalysis,
    get_error_analyzer,
    analyze_error
)
from .embeddings import (
    get_embedding,
    cosine_similarity,
    SemanticIndex,
    get_backend_info
)
from .code_utils import (
    smart_truncate,
    extract_imports,
    extract_function_signatures,
    generate_code_summary
)

__all__ = [
    # 短期记忆
    'ShortTermMemory',
    'get_session_memory',
    'clear_session_memory',
    # 长期记忆
    'LongTermMemory', 
    'get_long_term_memory',
    'LearnedExperience',
    # 错误分析
    'ErrorAnalyzer',
    'ErrorAnalysis',
    'get_error_analyzer',
    'analyze_error',
    # 嵌入
    'get_embedding',
    'cosine_similarity',
    'SemanticIndex',
    'get_backend_info',
    # 代码工具
    'smart_truncate',
    'extract_imports',
    'extract_function_signatures',
    'generate_code_summary'
]
