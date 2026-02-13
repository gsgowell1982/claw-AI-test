"""
Code Utils - 代码处理工具

版本: v2.5.3
功能:
- 智能代码截断（保留核心结构）
- 提取函数定义
- 提取导入语句
- 代码摘要生成
"""

import re
from typing import Optional, List, Tuple, Dict
import logging

logger = logging.getLogger("OpenClaw.Memory.CodeUtils")


def smart_truncate(
    code: str,
    max_lines: int = 50,
    max_chars: int = 2000,
    preserve_structure: bool = True
) -> str:
    """
    智能截断代码
    
    保留代码的核心结构：
    1. 保留导入语句
    2. 保留函数/类定义（至少签名）
    3. 保留关键注释
    4. 截断函数体中间部分
    
    Args:
        code: 原始代码
        max_lines: 最大行数
        max_chars: 最大字符数
        preserve_structure: 是否保留结构
        
    Returns:
        截断后的代码
    """
    if not code:
        return ""
    
    lines = code.split('\n')
    
    # 如果在限制内，直接返回
    if len(lines) <= max_lines and len(code) <= max_chars:
        return code
    
    if not preserve_structure:
        # 简单按行截断
        truncated = '\n'.join(lines[:max_lines])
        if len(truncated) > max_chars:
            truncated = truncated[:max_chars]
        return truncated + "\n# ... (已截断)"
    
    # 智能截断
    result_lines = []
    current_chars = 0
    
    # 第一阶段：收集导入语句
    imports = []
    other_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')) and not stripped.startswith('#'):
            imports.append(line)
        else:
            other_lines.append(line)
    
    # 添加导入（限制数量）
    for imp in imports[:15]:  # 最多15个导入
        result_lines.append(imp)
        current_chars += len(imp) + 1
    
    if imports:
        result_lines.append("")
        current_chars += 1
    
    # 第二阶段：提取函数和类定义
    in_definition = False
    definition_depth = 0
    definition_lines = []
    current_definition = []
    
    for line in other_lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        
        # 检测函数或类定义开始
        if re.match(r'^(def |class |async def )', stripped):
            if current_definition:
                definition_lines.append(current_definition)
            current_definition = [line]
            in_definition = True
            definition_depth = indent
        elif in_definition:
            # 检查是否还在定义内
            if stripped and indent <= definition_depth and not stripped.startswith(('#', '"""', "'''")):
                # 定义结束
                definition_lines.append(current_definition)
                current_definition = []
                in_definition = False
                
                # 检查是否是新的定义
                if re.match(r'^(def |class |async def )', stripped):
                    current_definition = [line]
                    in_definition = True
                    definition_depth = indent
            else:
                current_definition.append(line)
        else:
            # 非定义部分的代码
            if stripped and not stripped.startswith('#'):
                # 保留主要逻辑行
                if len(result_lines) < max_lines // 2:
                    result_lines.append(line)
                    current_chars += len(line) + 1
    
    if current_definition:
        definition_lines.append(current_definition)
    
    # 第三阶段：添加函数定义（智能截断）
    remaining_lines = max_lines - len(result_lines)
    remaining_chars = max_chars - current_chars
    
    for definition in definition_lines:
        if remaining_lines <= 2 or remaining_chars <= 100:
            break
        
        # 获取定义的签名（第一行和docstring）
        signature = definition[0]
        result_lines.append(signature)
        remaining_lines -= 1
        remaining_chars -= len(signature) + 1
        
        # 检查是否有 docstring
        if len(definition) > 1:
            second_line = definition[1].strip()
            if second_line.startswith(('"""', "'''")):
                # 添加 docstring
                docstring_lines = []
                in_docstring = True
                for dl in definition[1:]:
                    docstring_lines.append(dl)
                    if dl.strip().endswith(('"""', "'''")):
                        in_docstring = False
                        break
                
                for dl in docstring_lines[:3]:  # 最多3行docstring
                    result_lines.append(dl)
                    remaining_lines -= 1
                    remaining_chars -= len(dl) + 1
        
        # 如果函数体很长，添加省略标记
        if len(definition) > 5:
            indent = len(definition[0]) - len(definition[0].lstrip()) + 4
            result_lines.append(" " * indent + "# ... (函数体已省略)")
            remaining_lines -= 1
            remaining_chars -= indent + 20
        else:
            # 短函数完整保留
            for line in definition[1:]:
                if remaining_lines <= 0 or remaining_chars <= 0:
                    break
                result_lines.append(line)
                remaining_lines -= 1
                remaining_chars -= len(line) + 1
        
        result_lines.append("")
    
    # 添加截断标记
    if len(lines) > len(result_lines):
        result_lines.append(f"# ... (共 {len(lines)} 行，已截断显示)")
    
    return '\n'.join(result_lines)


def extract_imports(code: str) -> List[str]:
    """
    提取代码中的导入语句
    
    Args:
        code: 源代码
        
    Returns:
        导入语句列表
    """
    imports = []
    for line in code.split('\n'):
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')):
            imports.append(stripped)
    return imports


def extract_function_signatures(code: str) -> List[Dict[str, str]]:
    """
    提取函数签名
    
    Args:
        code: 源代码
        
    Returns:
        [{"name": "func_name", "signature": "def func_name(...):", "docstring": "..."}, ...]
    """
    functions = []
    lines = code.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # 检测函数定义
        match = re.match(r'^(async\s+)?def\s+(\w+)\s*\(', stripped)
        if match:
            func_name = match.group(2)
            signature = stripped
            
            # 检查是否有 docstring
            docstring = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith(('"""', "'''")):
                    quote = next_line[:3]
                    if next_line.endswith(quote) and len(next_line) > 6:
                        docstring = next_line[3:-3]
                    else:
                        # 多行 docstring
                        doc_lines = [next_line[3:]]
                        j = i + 2
                        while j < len(lines):
                            dl = lines[j]
                            if quote in dl:
                                doc_lines.append(dl.split(quote)[0])
                                break
                            doc_lines.append(dl.strip())
                            j += 1
                        docstring = ' '.join(doc_lines)
            
            functions.append({
                "name": func_name,
                "signature": signature,
                "docstring": docstring[:200] if docstring else ""
            })
        
        i += 1
    
    return functions


def extract_core_logic(code: str, max_lines: int = 30) -> str:
    """
    提取代码的核心逻辑
    
    移除注释、空行，保留关键代码
    
    Args:
        code: 源代码
        max_lines: 最大行数
        
    Returns:
        核心逻辑代码
    """
    lines = code.split('\n')
    core_lines = []
    
    in_docstring = False
    docstring_char = None
    
    for line in lines:
        stripped = line.strip()
        
        # 跳过空行
        if not stripped:
            continue
        
        # 处理 docstring
        if not in_docstring:
            if stripped.startswith(('"""', "'''")):
                docstring_char = stripped[:3]
                if stripped.endswith(docstring_char) and len(stripped) > 6:
                    continue  # 单行 docstring
                in_docstring = True
                continue
        else:
            if docstring_char in stripped:
                in_docstring = False
            continue
        
        # 跳过单行注释
        if stripped.startswith('#'):
            continue
        
        core_lines.append(line)
        
        if len(core_lines) >= max_lines:
            break
    
    return '\n'.join(core_lines)


def generate_code_summary(code: str) -> str:
    """
    生成代码摘要
    
    Args:
        code: 源代码
        
    Returns:
        代码摘要文本
    """
    imports = extract_imports(code)
    functions = extract_function_signatures(code)
    
    parts = []
    
    if imports:
        parts.append(f"导入: {', '.join(imports[:5])}")
        if len(imports) > 5:
            parts.append(f"  (+{len(imports) - 5} more)")
    
    if functions:
        func_names = [f["name"] for f in functions]
        parts.append(f"函数: {', '.join(func_names[:5])}")
        if len(functions) > 5:
            parts.append(f"  (+{len(functions) - 5} more)")
    
    lines = code.split('\n')
    parts.append(f"共 {len(lines)} 行")
    
    return "; ".join(parts)
