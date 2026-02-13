"""
Long-term Memory - 长期记忆管理

版本: v2.5.3
功能:
- 持久化存储错误模式和解决方案
- 基于 Embedding 的语义级记忆检索
- 执行历史自动清理（30天过期）
- 智能代码截断
- 学习成功的修复策略

更新 v2.5.3:
- 新增 embedding 字段支持语义搜索
- 新增 vacuum_old_records() 清理过期数据
- 使用 smart_truncate 替代硬编码截断
"""

import sqlite3
import json
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import logging

from .embeddings import get_embedding, cosine_similarity, embedding_to_json, json_to_embedding
from .code_utils import smart_truncate, generate_code_summary

logger = logging.getLogger("OpenClaw.Memory.LongTerm")


# 配置常量
MAX_HISTORY_DAYS = 30  # 执行历史保留天数
MAX_HISTORY_RECORDS = 10000  # 执行历史最大记录数
SEMANTIC_SEARCH_THRESHOLD = 0.4  # 语义搜索相似度阈值


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


@dataclass 
class LearnedExperience:
    """学习到的经验"""
    id: int
    category: str
    trigger_pattern: str
    action: str
    outcome: str
    confidence: float
    use_count: int
    embedding: Optional[List[float]]
    created_at: str
    updated_at: str


class LongTermMemory:
    """
    长期记忆
    
    使用 SQLite 存储：
    1. 错误模式和解决方案
    2. 执行历史（带自动清理）
    3. 学习到的经验（带语义检索）
    """
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "long_term_memory.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        self._migrate_database()  # 执行迁移
        
        # 启动时清理过期数据
        self.vacuum_old_records()
        
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
            
            # 执行历史表（添加索引优化清理性能）
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
            
            # 创建索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_execution_history_created_at 
                ON execution_history(created_at)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_execution_history_tool_name 
                ON execution_history(tool_name)
            ''')
            
            # 学习经验表（v2.5.3 新增 embedding 字段）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS learned_experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    trigger_pattern TEXT,
                    action TEXT,
                    outcome TEXT,
                    confidence REAL DEFAULT 0.5,
                    use_count INTEGER DEFAULT 0,
                    embedding TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def _migrate_database(self) -> None:
        """数据库迁移"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 检查 learned_experiences 是否有 embedding 字段
            cursor.execute("PRAGMA table_info(learned_experiences)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'embedding' not in columns:
                logger.info("[LongTerm] 迁移: 添加 embedding 字段")
                cursor.execute('ALTER TABLE learned_experiences ADD COLUMN embedding TEXT')
                conn.commit()
    
    def _get_error_hash(self, error_type: str, error_message: str) -> str:
        """生成错误的唯一哈希"""
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
        
        # 智能截断解决方案代码
        if solution_code:
            solution_code = smart_truncate(solution_code, max_lines=100, max_chars=5000)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT id, fail_count FROM error_patterns WHERE error_hash = ?',
                (error_hash,)
            )
            existing = cursor.fetchone()
            
            if existing:
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
        
        # 智能截断解决方案代码
        if solution_code:
            solution_code = smart_truncate(solution_code, max_lines=100, max_chars=5000)
        
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
        # 截断大型结果
        result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        if len(result_str) > 5000:
            result_str = result_str[:5000] + "... (已截断)"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO execution_history 
                (tool_name, arguments, result, success, error_type, error_message, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                tool_name,
                json.dumps(arguments, ensure_ascii=False),
                result_str,
                1 if success else 0,
                error_type,
                error_message,
                duration_ms
            ))
            conn.commit()
    
    def vacuum_old_records(self) -> Dict[str, int]:
        """
        清理过期数据
        
        策略:
        1. 删除超过 30 天的执行历史
        2. 保留高频工具的最近 N 条记录
        3. 执行 SQLite VACUUM 优化存储
        
        Returns:
            {"deleted_history": 删除数, "remaining": 剩余数}
        """
        logger.info("[LongTerm] 开始清理过期数据...")
        
        cutoff_date = (datetime.now() - timedelta(days=MAX_HISTORY_DAYS)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 统计当前记录数
            cursor.execute('SELECT COUNT(*) FROM execution_history')
            before_count = cursor.fetchone()[0]
            
            # 删除过期记录
            cursor.execute('''
                DELETE FROM execution_history 
                WHERE created_at < ?
            ''', (cutoff_date,))
            
            deleted_by_date = cursor.rowcount
            
            # 如果仍然超过最大数量，删除最旧的记录
            cursor.execute('SELECT COUNT(*) FROM execution_history')
            current_count = cursor.fetchone()[0]
            
            deleted_by_limit = 0
            if current_count > MAX_HISTORY_RECORDS:
                excess = current_count - MAX_HISTORY_RECORDS
                cursor.execute('''
                    DELETE FROM execution_history 
                    WHERE id IN (
                        SELECT id FROM execution_history 
                        ORDER BY created_at ASC 
                        LIMIT ?
                    )
                ''', (excess,))
                deleted_by_limit = cursor.rowcount
            
            conn.commit()
            
            # 获取最终记录数
            cursor.execute('SELECT COUNT(*) FROM execution_history')
            after_count = cursor.fetchone()[0]
            
            # VACUUM 优化数据库
            try:
                conn.execute('VACUUM')
            except Exception as e:
                logger.warning(f"[LongTerm] VACUUM 失败: {e}")
        
        total_deleted = deleted_by_date + deleted_by_limit
        
        if total_deleted > 0:
            logger.info(f"[LongTerm] 清理完成: 删除 {total_deleted} 条记录 "
                       f"(过期: {deleted_by_date}, 超限: {deleted_by_limit}), "
                       f"剩余 {after_count} 条")
        
        return {
            "deleted_history": total_deleted,
            "deleted_by_date": deleted_by_date,
            "deleted_by_limit": deleted_by_limit,
            "remaining": after_count
        }
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM error_patterns')
            total_patterns = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM error_patterns WHERE solution IS NOT NULL')
            solved_patterns = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM execution_history')
            total_executions = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM learned_experiences')
            total_experiences = cursor.fetchone()[0]
            
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
                "total_executions": total_executions,
                "total_experiences": total_experiences,
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
            # 使用智能截断
            truncated_code = smart_truncate(pattern.solution_code, max_lines=30, max_chars=1500)
            parts.append(f"\n**参考代码**：\n```python\n{truncated_code}\n```")
        
        return "\n".join(parts)
    
    def learn_from_success(
        self,
        category: str,
        trigger: str,
        action: str,
        outcome: str
    ) -> None:
        """
        从成功经验中学习
        
        自动生成 embedding 以支持语义检索
        """
        # 生成文本表示和 embedding
        text_representation = f"{category}: {trigger} -> {action} => {outcome}"
        embedding = get_embedding(text_representation)
        embedding_json = embedding_to_json(embedding)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, confidence, use_count FROM learned_experiences
                WHERE category = ? AND trigger_pattern = ?
            ''', (category, trigger))
            
            existing = cursor.fetchone()
            
            if existing:
                new_confidence = min(1.0, existing[1] + 0.1)
                cursor.execute('''
                    UPDATE learned_experiences
                    SET confidence = ?, use_count = use_count + 1, 
                        embedding = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (new_confidence, embedding_json, existing[0]))
            else:
                cursor.execute('''
                    INSERT INTO learned_experiences
                    (category, trigger_pattern, action, outcome, confidence, use_count, embedding)
                    VALUES (?, ?, ?, ?, 0.5, 1, ?)
                ''', (category, trigger, action, outcome, embedding_json))
            
            conn.commit()
            logger.info(f"[LongTerm] 学习经验: {category} - {trigger[:50]}")
    
    def search_experiences_semantic(
        self,
        query: str,
        category: Optional[str] = None,
        top_k: int = 5,
        threshold: float = SEMANTIC_SEARCH_THRESHOLD
    ) -> List[LearnedExperience]:
        """
        语义搜索经验
        
        基于 embedding 相似度查找相关经验，
        即使没有精确的 error_type 匹配也能找到相关解决方案
        
        Args:
            query: 查询文本（可以是用户问题、错误描述等）
            category: 可选的类别过滤
            top_k: 返回数量
            threshold: 相似度阈值
            
        Returns:
            相关经验列表，按相似度排序
        """
        query_embedding = get_embedding(query)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if category:
                cursor.execute('''
                    SELECT id, category, trigger_pattern, action, outcome, 
                           confidence, use_count, embedding, created_at, updated_at
                    FROM learned_experiences
                    WHERE category = ? AND embedding IS NOT NULL
                ''', (category,))
            else:
                cursor.execute('''
                    SELECT id, category, trigger_pattern, action, outcome, 
                           confidence, use_count, embedding, created_at, updated_at
                    FROM learned_experiences
                    WHERE embedding IS NOT NULL
                ''')
            
            rows = cursor.fetchall()
        
        # 计算相似度并排序
        results = []
        for row in rows:
            exp_embedding = json_to_embedding(row[7])
            if exp_embedding:
                similarity = cosine_similarity(query_embedding, exp_embedding)
                if similarity >= threshold:
                    exp = LearnedExperience(
                        id=row[0],
                        category=row[1],
                        trigger_pattern=row[2],
                        action=row[3],
                        outcome=row[4],
                        confidence=row[5],
                        use_count=row[6],
                        embedding=exp_embedding,
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    results.append((exp, similarity))
        
        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        if results:
            logger.info(f"[LongTerm] 语义搜索找到 {len(results[:top_k])} 个相关经验")
        
        return [exp for exp, _ in results[:top_k]]
    
    def get_relevant_context(self, query: str, max_items: int = 3) -> str:
        """
        获取与查询相关的上下文（用于 LLM）
        
        综合使用语义搜索和关键词匹配
        
        Args:
            query: 查询文本
            max_items: 最大返回项数
            
        Returns:
            格式化的上下文字符串
        """
        experiences = self.search_experiences_semantic(query, top_k=max_items)
        
        if not experiences:
            return ""
        
        parts = ["## 相关历史经验"]
        
        for i, exp in enumerate(experiences, 1):
            parts.append(f"\n### 经验 {i} (置信度: {exp.confidence:.0%}, 使用次数: {exp.use_count})")
            parts.append(f"**场景**: {exp.trigger_pattern}")
            parts.append(f"**操作**: {exp.action}")
            parts.append(f"**结果**: {exp.outcome}")
        
        return "\n".join(parts)
    
    def get_tool_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取工具使用统计
        
        Args:
            days: 统计天数
            
        Returns:
            统计信息
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 按工具统计
            cursor.execute('''
                SELECT tool_name, 
                       COUNT(*) as total,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                       AVG(duration_ms) as avg_duration
                FROM execution_history
                WHERE created_at >= ?
                GROUP BY tool_name
                ORDER BY total DESC
            ''', (cutoff_date,))
            
            tool_stats = cursor.fetchall()
            
            return {
                "period_days": days,
                "tools": [
                    {
                        "name": name,
                        "total": total,
                        "successes": successes,
                        "success_rate": successes / total if total > 0 else 0,
                        "avg_duration_ms": avg_duration or 0
                    }
                    for name, total, successes, avg_duration in tool_stats
                ]
            }


# 全局长期记忆实例
_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """获取长期记忆实例"""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory
