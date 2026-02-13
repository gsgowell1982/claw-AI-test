"""
Long-term Memory - 长期记忆管理

版本: v2.5.1
功能:
- 持久化存储错误模式和解决方案
- 检索历史经验
- 学习成功的修复策略
"""

import sqlite3
import json
import hashlib
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger("OpenClaw.Memory.LongTerm")


@dataclass
class ErrorPattern:
    """错误模式"""
    id: int
    error_type: str  # 错误类型 (ImportError, SyntaxError, etc.)
    error_message: str  # 错误消息
    context: str  # 上下文（工具、参数等）
    solution: Optional[str]  # 解决方案
    solution_code: Optional[str]  # 修复代码
    success_count: int  # 成功次数
    fail_count: int  # 失败次数
    created_at: str
    updated_at: str


@dataclass
class ExecutionHistory:
    """执行历史"""
    id: int
    tool_name: str
    arguments: str  # JSON
    result: str  # JSON
    success: bool
    error_type: Optional[str]
    error_message: Optional[str]
    duration_ms: float
    created_at: str


class LongTermMemory:
    """
    长期记忆
    
    使用 SQLite 存储：
    1. 错误模式和解决方案
    2. 执行历史
    3. 学习到的经验
    """
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "long_term_memory.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        logger.info(f"[LongTerm] 数据库初始化: {self.db_path}")
    
    def _init_database(self) -> None:
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 错误模式表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS error_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    error_hash TEXT UNIQUE,
                    context TEXT,
                    solution TEXT,
                    solution_code TEXT,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 执行历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS execution_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    arguments TEXT,
                    result TEXT,
                    success INTEGER,
                    error_type TEXT,
                    error_message TEXT,
                    duration_ms REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 学习经验表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS learned_experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    trigger_pattern TEXT,
                    action TEXT,
                    outcome TEXT,
                    confidence REAL DEFAULT 0.5,
                    use_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def _get_error_hash(self, error_type: str, error_message: str) -> str:
        """生成错误的唯一哈希"""
        # 提取错误消息的关键部分（去除具体路径等）
        import re
        normalized = re.sub(r"'[^']*'", "'X'", error_message)
        normalized = re.sub(r'"[^"]*"', '"X"', normalized)
        normalized = re.sub(r'\d+', 'N', normalized)
        
        content = f"{error_type}:{normalized}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def record_error(
        self,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None,
        solution: Optional[str] = None,
        solution_code: Optional[str] = None
    ) -> int:
        """记录错误模式"""
        error_hash = self._get_error_hash(error_type, error_message)
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 检查是否已存在
            cursor.execute(
                'SELECT id, fail_count FROM error_patterns WHERE error_hash = ?',
                (error_hash,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # 更新现有记录
                cursor.execute('''
                    UPDATE error_patterns 
                    SET fail_count = fail_count + 1,
                        context = COALESCE(?, context),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (context_str or None, existing[0]))
                record_id = existing[0]
                logger.info(f"[LongTerm] 更新错误模式: {error_type}, 失败次数: {existing[1] + 1}")
            else:
                # 插入新记录
                cursor.execute('''
                    INSERT INTO error_patterns 
                    (error_type, error_message, error_hash, context, solution, solution_code, fail_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                ''', (error_type, error_message, error_hash, context_str, solution, solution_code))
                record_id = cursor.lastrowid
                logger.info(f"[LongTerm] 记录新错误模式: {error_type}")
            
            conn.commit()
            return record_id
    
    def record_solution(
        self,
        error_type: str,
        error_message: str,
        solution: str,
        solution_code: Optional[str] = None,
        success: bool = True
    ) -> None:
        """记录解决方案"""
        error_hash = self._get_error_hash(error_type, error_message)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if success:
                cursor.execute('''
                    UPDATE error_patterns 
                    SET solution = ?,
                        solution_code = ?,
                        success_count = success_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE error_hash = ?
                ''', (solution, solution_code, error_hash))
            else:
                cursor.execute('''
                    UPDATE error_patterns 
                    SET fail_count = fail_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE error_hash = ?
                ''', (error_hash,))
            
            conn.commit()
            logger.info(f"[LongTerm] 记录解决方案: {error_type}, 成功: {success}")
    
    def find_similar_error(
        self,
        error_type: str,
        error_message: str
    ) -> Optional[ErrorPattern]:
        """查找相似的错误模式"""
        error_hash = self._get_error_hash(error_type, error_message)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 精确匹配
            cursor.execute('''
                SELECT id, error_type, error_message, context, solution, solution_code,
                       success_count, fail_count, created_at, updated_at
                FROM error_patterns 
                WHERE error_hash = ? AND solution IS NOT NULL
                ORDER BY success_count DESC
                LIMIT 1
            ''', (error_hash,))
            
            row = cursor.fetchone()
            if row:
                logger.info(f"[LongTerm] 找到精确匹配的错误模式: {error_type}")
                return ErrorPattern(*row)
            
            # 模糊匹配（基于错误类型）
            cursor.execute('''
                SELECT id, error_type, error_message, context, solution, solution_code,
                       success_count, fail_count, created_at, updated_at
                FROM error_patterns 
                WHERE error_type = ? AND solution IS NOT NULL
                ORDER BY success_count DESC
                LIMIT 1
            ''', (error_type,))
            
            row = cursor.fetchone()
            if row:
                logger.info(f"[LongTerm] 找到类型匹配的错误模式: {error_type}")
                return ErrorPattern(*row)
            
            return None
    
    def record_execution(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        success: bool,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: float = 0
    ) -> None:
        """记录执行历史"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO execution_history 
                (tool_name, arguments, result, success, error_type, error_message, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                tool_name,
                json.dumps(arguments, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result),
                1 if success else 0,
                error_type,
                error_message,
                duration_ms
            ))
            conn.commit()
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 总体统计
            cursor.execute('SELECT COUNT(*) FROM error_patterns')
            total_patterns = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM error_patterns WHERE solution IS NOT NULL')
            solved_patterns = cursor.fetchone()[0]
            
            # 按类型统计
            cursor.execute('''
                SELECT error_type, COUNT(*), SUM(success_count), SUM(fail_count)
                FROM error_patterns
                GROUP BY error_type
                ORDER BY COUNT(*) DESC
                LIMIT 10
            ''')
            by_type = cursor.fetchall()
            
            return {
                "total_patterns": total_patterns,
                "solved_patterns": solved_patterns,
                "by_type": [
                    {"type": t, "count": c, "successes": s or 0, "failures": f or 0}
                    for t, c, s, f in by_type
                ]
            }
    
    def get_context_for_error(self, error_type: str, error_message: str) -> str:
        """获取错误的上下文信息（用于 LLM）"""
        pattern = self.find_similar_error(error_type, error_message)
        
        if not pattern:
            return ""
        
        parts = [f"## 历史经验：{error_type}"]
        parts.append(f"\n**之前遇到过类似错误** (成功修复 {pattern.success_count} 次)")
        
        if pattern.solution:
            parts.append(f"\n**解决方案**：{pattern.solution}")
        
        if pattern.solution_code:
            parts.append(f"\n**参考代码**：\n```python\n{pattern.solution_code[:500]}\n```")
        
        return "\n".join(parts)
    
    def learn_from_success(
        self,
        category: str,
        trigger: str,
        action: str,
        outcome: str
    ) -> None:
        """从成功经验中学习"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 检查是否已存在相似经验
            cursor.execute('''
                SELECT id, confidence, use_count FROM learned_experiences
                WHERE category = ? AND trigger_pattern = ?
            ''', (category, trigger))
            
            existing = cursor.fetchone()
            
            if existing:
                # 增加置信度
                new_confidence = min(1.0, existing[1] + 0.1)
                cursor.execute('''
                    UPDATE learned_experiences
                    SET confidence = ?, use_count = use_count + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (new_confidence, existing[0]))
            else:
                # 添加新经验
                cursor.execute('''
                    INSERT INTO learned_experiences
                    (category, trigger_pattern, action, outcome, confidence, use_count)
                    VALUES (?, ?, ?, ?, 0.5, 1)
                ''', (category, trigger, action, outcome))
            
            conn.commit()
            logger.info(f"[LongTerm] 学习经验: {category} - {trigger[:50]}")


# 全局长期记忆实例
_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """获取长期记忆实例"""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory
