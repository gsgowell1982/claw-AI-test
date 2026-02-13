"""
Error Analyzer - 错误分析器

版本: v2.5.1
功能:
- 分析代码执行错误
- 提取错误原因
- 建议修复方案
- 生成修复后的代码
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger("OpenClaw.Memory.ErrorAnalyzer")


@dataclass
class ErrorAnalysis:
    """错误分析结果"""
    error_type: str  # ImportError, SyntaxError, etc.
    error_message: str
    error_location: Optional[str]  # 文件:行号
    root_cause: str  # 根本原因
    suggestion: str  # 修复建议
    fix_type: str  # "import", "syntax", "logic", "runtime", "unknown"
    confidence: float  # 置信度 0-1
    can_auto_fix: bool  # 是否可以自动修复
    fix_code: Optional[str]  # 修复代码（如果可自动修复）


class ErrorAnalyzer:
    """
    错误分析器
    
    分析 Python 代码执行错误，提供修复建议
    """
    
    # 常见错误模式
    ERROR_PATTERNS = {
        "ImportError": {
            r"cannot import name '([^']+)' from '([^']+)'": {
                "cause": "导入的名称在模块中不存在或已更改",
                "fix_type": "import",
                "suggestion": "检查模块文档，确认正确的导入路径"
            },
            r"No module named '([^']+)'": {
                "cause": "模块未安装",
                "fix_type": "import",
                "suggestion": "安装缺失的模块"
            }
        },
        "ModuleNotFoundError": {
            r"No module named '([^']+)'": {
                "cause": "模块未安装",
                "fix_type": "import",
                "suggestion": "使用 pip install 安装模块"
            }
        },
        "SyntaxError": {
            r"invalid syntax": {
                "cause": "语法错误",
                "fix_type": "syntax",
                "suggestion": "检查代码语法，特别是括号、冒号、缩进"
            },
            r"unexpected EOF while parsing": {
                "cause": "代码不完整，缺少闭合符号",
                "fix_type": "syntax",
                "suggestion": "检查括号、引号是否配对"
            }
        },
        "IndentationError": {
            r".*": {
                "cause": "缩进错误",
                "fix_type": "syntax",
                "suggestion": "检查代码缩进，使用一致的空格或制表符"
            }
        },
        "NameError": {
            r"name '([^']+)' is not defined": {
                "cause": "使用了未定义的变量",
                "fix_type": "logic",
                "suggestion": "检查变量名拼写，确保在使用前定义"
            }
        },
        "TypeError": {
            r"'([^']+)' object is not subscriptable": {
                "cause": "尝试对不支持索引的对象使用索引",
                "fix_type": "logic",
                "suggestion": "检查对象类型，确保它支持索引操作"
            },
            r"'([^']+)' object is not callable": {
                "cause": "尝试调用不可调用的对象",
                "fix_type": "logic",
                "suggestion": "检查是否误用了括号，或对象类型是否正确"
            }
        },
        "FileNotFoundError": {
            r".*": {
                "cause": "文件或目录不存在",
                "fix_type": "runtime",
                "suggestion": "检查文件路径是否正确"
            }
        },
        "AttributeError": {
            r"'([^']+)' object has no attribute '([^']+)'": {
                "cause": "对象没有指定的属性或方法",
                "fix_type": "logic",
                "suggestion": "检查对象类型和可用的属性/方法"
            }
        }
    }
    
    # 已知的导入修复
    IMPORT_FIXES = {
        ("pptx.dml.color", "RgbColor"): {
            "suggestion": "RgbColor 在 python-pptx 1.0+ 中已移除，使用 pptx.util 中的颜色工具",
            "fix_code": """# 不需要导入 RgbColor
# 使用 pptx.dml.color.Rgb 或直接使用颜色值
from pptx.util import Inches, Pt"""
        },
        ("PIL", None): {
            "suggestion": "PIL 已被 Pillow 替代",
            "fix_code": "from PIL import Image  # 需要安装 Pillow: pip install Pillow"
        }
    }
    
    def analyze(self, error_output: str, original_code: Optional[str] = None) -> ErrorAnalysis:
        """
        分析错误输出
        
        Args:
            error_output: 错误输出文本
            original_code: 原始代码（可选）
            
        Returns:
            ErrorAnalysis 结果
        """
        logger.info("[ErrorAnalyzer] 开始分析错误...")
        
        # 提取错误类型和消息
        error_type, error_message, error_location = self._extract_error_info(error_output)
        
        if not error_type:
            return ErrorAnalysis(
                error_type="Unknown",
                error_message=error_output[:200],
                error_location=None,
                root_cause="无法识别错误类型",
                suggestion="请检查完整错误信息",
                fix_type="unknown",
                confidence=0.1,
                can_auto_fix=False,
                fix_code=None
            )
        
        # 查找匹配的错误模式
        analysis = self._match_error_pattern(error_type, error_message)
        
        # 检查是否有已知的修复方案
        fix_info = self._get_known_fix(error_type, error_message, original_code)
        
        if fix_info:
            analysis.suggestion = fix_info.get("suggestion", analysis.suggestion)
            analysis.fix_code = fix_info.get("fix_code")
            analysis.can_auto_fix = fix_info.get("can_auto_fix", False)
            analysis.confidence = 0.9
        
        analysis.error_location = error_location
        
        logger.info(f"[ErrorAnalyzer] 分析完成: {error_type}, 置信度: {analysis.confidence}")
        
        return analysis
    
    def _extract_error_info(self, error_output: str) -> Tuple[Optional[str], str, Optional[str]]:
        """提取错误信息"""
        lines = error_output.strip().split('\n')
        
        error_type = None
        error_message = ""
        error_location = None
        
        for i, line in enumerate(lines):
            # 匹配错误类型行
            error_match = re.match(r'^(\w+Error|\w+Exception):\s*(.*)$', line)
            if error_match:
                error_type = error_match.group(1)
                error_message = error_match.group(2)
                
                # 尝试获取位置信息
                if i > 0:
                    for prev_line in reversed(lines[:i]):
                        loc_match = re.search(r'File "([^"]+)", line (\d+)', prev_line)
                        if loc_match:
                            error_location = f"{loc_match.group(1)}:{loc_match.group(2)}"
                            break
                break
        
        return error_type, error_message, error_location
    
    def _match_error_pattern(self, error_type: str, error_message: str) -> ErrorAnalysis:
        """匹配错误模式"""
        patterns = self.ERROR_PATTERNS.get(error_type, {})
        
        for pattern, info in patterns.items():
            if re.search(pattern, error_message):
                return ErrorAnalysis(
                    error_type=error_type,
                    error_message=error_message,
                    error_location=None,
                    root_cause=info["cause"],
                    suggestion=info["suggestion"],
                    fix_type=info["fix_type"],
                    confidence=0.7,
                    can_auto_fix=False,
                    fix_code=None
                )
        
        # 默认分析
        return ErrorAnalysis(
            error_type=error_type,
            error_message=error_message,
            error_location=None,
            root_cause=f"{error_type}: {error_message}",
            suggestion="检查代码逻辑和错误消息",
            fix_type="unknown",
            confidence=0.3,
            can_auto_fix=False,
            fix_code=None
        )
    
    def _get_known_fix(
        self,
        error_type: str,
        error_message: str,
        original_code: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """获取已知的修复方案"""
        
        # ImportError 特殊处理
        if error_type == "ImportError":
            match = re.search(r"cannot import name '([^']+)' from '([^']+)'", error_message)
            if match:
                name, module = match.groups()
                key = (module, name)
                if key in self.IMPORT_FIXES:
                    return self.IMPORT_FIXES[key]
                
                # 检查部分匹配
                for (mod, nm), fix in self.IMPORT_FIXES.items():
                    if module.startswith(mod) or mod.startswith(module):
                        return fix
        
        return None
    
    def generate_fix_prompt(self, analysis: ErrorAnalysis, original_code: str) -> str:
        """生成修复提示（用于 LLM）"""
        prompt = f"""## 代码执行错误分析

**错误类型**: {analysis.error_type}
**错误消息**: {analysis.error_message}
**错误位置**: {analysis.error_location or "未知"}
**根本原因**: {analysis.root_cause}
**修复建议**: {analysis.suggestion}

**原始代码**:
```python
{original_code[:2000]}
```

请分析上述错误，并提供修复后的完整代码。修复时请注意：
1. 保持代码的原有功能
2. 只修复导致错误的部分
3. 添加必要的注释说明修改
"""
        
        if analysis.fix_code:
            prompt += f"""
**参考修复**:
```python
{analysis.fix_code}
```
"""
        
        return prompt


# 全局错误分析器实例
_error_analyzer: Optional[ErrorAnalyzer] = None


def get_error_analyzer() -> ErrorAnalyzer:
    """获取错误分析器实例"""
    global _error_analyzer
    if _error_analyzer is None:
        _error_analyzer = ErrorAnalyzer()
    return _error_analyzer


def analyze_error(error_output: str, original_code: Optional[str] = None) -> ErrorAnalysis:
    """便捷函数：分析错误"""
    return get_error_analyzer().analyze(error_output, original_code)
