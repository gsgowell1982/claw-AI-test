"""
File Tools - 文件操作工具

版本: v2.3
提供:
- 列出目录内容
- 读取文件
- 写入文件
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..schema import ToolDefinition, ToolParameter, ParameterType


# 项目根目录和安全输出目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
SAFE_OUTPUT_DIR = PROJECT_ROOT / "Test"


def list_files(path: str = ".") -> Dict[str, Any]:
    """
    列出指定目录的文件和文件夹
    
    Args:
        path: 目录路径，默认为项目根目录
        
    Returns:
        包含文件列表的字典
    """
    try:
        # 解析路径
        if path == "." or path == "":
            target_path = PROJECT_ROOT
        else:
            target_path = PROJECT_ROOT / path
        
        target_path = target_path.resolve()
        
        # 安全检查：确保在项目目录内
        if not str(target_path).startswith(str(PROJECT_ROOT)):
            return {
                "success": False,
                "error": "不允许访问项目目录之外的路径"
            }
        
        if not target_path.exists():
            return {
                "success": False,
                "error": f"路径不存在: {path}"
            }
        
        if not target_path.is_dir():
            return {
                "success": False,
                "error": f"不是目录: {path}"
            }
        
        # 列出内容
        items = []
        for item in sorted(target_path.iterdir()):
            # 跳过隐藏文件和 __pycache__
            if item.name.startswith('.') or item.name == '__pycache__':
                continue
            
            item_info = {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
            }
            
            if item.is_file():
                item_info["size"] = item.stat().st_size
            
            items.append(item_info)
        
        return {
            "success": True,
            "path": str(target_path.relative_to(PROJECT_ROOT)),
            "count": len(items),
            "items": items
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def read_file(path: str) -> Dict[str, Any]:
    """
    读取文件内容
    
    Args:
        path: 文件路径（相对于项目根目录）
        
    Returns:
        包含文件内容的字典
    """
    try:
        # 解析路径
        target_path = PROJECT_ROOT / path
        target_path = target_path.resolve()
        
        # 安全检查
        if not str(target_path).startswith(str(PROJECT_ROOT)):
            return {
                "success": False,
                "error": "不允许访问项目目录之外的文件"
            }
        
        if not target_path.exists():
            return {
                "success": False,
                "error": f"文件不存在: {path}"
            }
        
        if not target_path.is_file():
            return {
                "success": False,
                "error": f"不是文件: {path}"
            }
        
        # 读取文件
        content = target_path.read_text(encoding='utf-8')
        
        return {
            "success": True,
            "path": path,
            "size": len(content),
            "content": content
        }
    except UnicodeDecodeError:
        return {
            "success": False,
            "error": "无法读取二进制文件"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def write_file(filename: str, content: str) -> Dict[str, Any]:
    """
    将内容写入文件（保存到 Test 目录）
    
    Args:
        filename: 文件名（将保存到 Test 目录）
        content: 文件内容
        
    Returns:
        操作结果
    """
    try:
        # 确保输出目录存在
        SAFE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # 安全处理文件名
        safe_filename = Path(filename).name  # 只取文件名部分
        target_path = SAFE_OUTPUT_DIR / safe_filename
        
        # 写入文件
        target_path.write_text(content, encoding='utf-8')
        
        return {
            "success": True,
            "path": f"Test/{safe_filename}",
            "size": len(content),
            "message": f"文件已保存到 Test/{safe_filename}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============== 工具定义 ==============

LIST_FILES_TOOL = ToolDefinition(
    name="list_files",
    description="列出指定目录的文件和文件夹",
    parameters=[
        ToolParameter(
            name="path",
            type=ParameterType.STRING,
            description="目录路径，相对于项目根目录，默认为根目录",
            required=False,
            default="."
        )
    ],
    handler=list_files,
    category="file"
)

READ_FILE_TOOL = ToolDefinition(
    name="read_file",
    description="读取文件内容",
    parameters=[
        ToolParameter(
            name="path",
            type=ParameterType.STRING,
            description="文件路径，相对于项目根目录",
            required=True
        )
    ],
    handler=read_file,
    category="file"
)

WRITE_FILE_TOOL = ToolDefinition(
    name="write_file",
    description="将代码或文本写入文件（文件将保存到 Test 目录）",
    parameters=[
        ToolParameter(
            name="filename",
            type=ParameterType.STRING,
            description="文件名（如 hello.py）",
            required=True
        ),
        ToolParameter(
            name="content",
            type=ParameterType.STRING,
            description="要写入的文件内容",
            required=True
        )
    ],
    handler=write_file,
    category="file"
)


# 导出所有文件工具
FILE_TOOLS = [LIST_FILES_TOOL, READ_FILE_TOOL, WRITE_FILE_TOOL]


def get_file_tools() -> List[ToolDefinition]:
    """获取所有文件操作工具"""
    return FILE_TOOLS
