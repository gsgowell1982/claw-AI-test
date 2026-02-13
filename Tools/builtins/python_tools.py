"""
Python Tools - Python 代码执行与包管理工具

版本: v2.5
功能:
- 检查 Python 包是否安装
- 安装 Python 包
- 执行 Python 代码（带自动清理）
- 创建并执行临时脚本
"""

import subprocess
import sys
import os
import tempfile
import importlib
import importlib.util
from typing import Optional, List, Dict, Any
from pathlib import Path

from ..schema import ToolDefinition, ToolParameter, ParameterType

import logging
logger = logging.getLogger("OpenClaw.Python")


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


def check_package_installed(package_name: str) -> Dict[str, Any]:
    """
    检查 Python 包是否已安装
    
    Args:
        package_name: 包名称（如 python-pptx, pandas）
        
    Returns:
        检查结果
    """
    logger.info(f"[Python] 检查包: {package_name}")
    
    # 处理包名和导入名不同的情况
    import_name_mapping = {
        "python-pptx": "pptx",
        "Pillow": "PIL",
        "opencv-python": "cv2",
        "scikit-learn": "sklearn",
        "beautifulsoup4": "bs4",
    }
    
    import_name = import_name_mapping.get(package_name, package_name.replace("-", "_"))
    
    try:
        spec = importlib.util.find_spec(import_name)
        if spec is not None:
            # 尝试获取版本
            try:
                module = importlib.import_module(import_name)
                version = getattr(module, "__version__", "未知")
            except:
                version = "已安装"
            
            logger.info(f"[Python] 包 {package_name} 已安装，版本: {version}")
            return {
                "success": True,
                "installed": True,
                "package": package_name,
                "version": version,
                "message": f"✅ 包 {package_name} 已安装（版本: {version}）"
            }
        else:
            logger.info(f"[Python] 包 {package_name} 未安装")
            return {
                "success": True,
                "installed": False,
                "package": package_name,
                "message": f"❌ 包 {package_name} 未安装。是否需要安装？请回复'是'或'安装'来确认安装。"
            }
    except Exception as e:
        logger.error(f"[Python] 检查包失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "package": package_name
        }


def install_python_package(package_name: str, upgrade: bool = False) -> Dict[str, Any]:
    """
    安装 Python 包
    
    Args:
        package_name: 包名称
        upgrade: 是否升级已安装的包
        
    Returns:
        安装结果
    """
    logger.info(f"[Python] 安装包: {package_name}")
    
    try:
        # 使用 subprocess 调用 pip
        cmd = [sys.executable, "-m", "pip", "install"]
        if upgrade:
            cmd.append("--upgrade")
        cmd.append(package_name)
        
        logger.info(f"[Python] 执行命令: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0:
            logger.info(f"[Python] 包 {package_name} 安装成功")
            return {
                "success": True,
                "package": package_name,
                "message": f"✅ 包 {package_name} 安装成功！",
                "output": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
            }
        else:
            logger.error(f"[Python] 包安装失败: {result.stderr}")
            return {
                "success": False,
                "package": package_name,
                "error": f"安装失败: {result.stderr[-500:] if len(result.stderr) > 500 else result.stderr}"
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "package": package_name,
            "error": "安装超时（超过5分钟）"
        }
    except Exception as e:
        logger.error(f"[Python] 安装异常: {e}")
        return {
            "success": False,
            "package": package_name,
            "error": str(e)
        }


def execute_python_code(
    code: str,
    description: str = "",
    working_directory: Optional[str] = None,
    timeout: int = 60
) -> Dict[str, Any]:
    """
    执行 Python 代码
    
    会创建临时脚本文件，执行后自动删除。
    
    Args:
        code: Python 代码内容
        description: 代码功能描述
        working_directory: 工作目录（相对于项目根目录）
        timeout: 执行超时时间（秒）
        
    Returns:
        执行结果
    """
    logger.info(f"[Python] 执行代码: {description or '临时脚本'}")
    
    # 确定工作目录
    if working_directory:
        work_dir = PROJECT_ROOT / working_directory
    else:
        work_dir = PROJECT_ROOT
    
    if not work_dir.exists():
        work_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建临时脚本文件
    temp_script = None
    try:
        # 在工作目录创建临时文件
        fd, temp_path = tempfile.mkstemp(suffix='.py', dir=str(work_dir), prefix='_temp_script_')
        os.close(fd)
        temp_script = Path(temp_path)
        
        # 写入代码
        temp_script.write_text(code, encoding='utf-8')
        logger.info(f"[Python] 临时脚本: {temp_script}")
        
        # 执行脚本
        result = subprocess.run(
            [sys.executable, str(temp_script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(work_dir)
        )
        
        output = result.stdout
        error = result.stderr
        
        if result.returncode == 0:
            logger.info(f"[Python] 代码执行成功")
            return {
                "success": True,
                "message": f"✅ 代码执行成功！",
                "description": description,
                "output": output[-2000:] if len(output) > 2000 else output,
                "return_code": 0
            }
        else:
            logger.error(f"[Python] 代码执行失败: {error}")
            
            # 检查是否是缺少包的错误
            missing_packages = _detect_missing_packages(error)
            if missing_packages:
                return {
                    "success": False,
                    "error": f"执行失败，缺少以下包: {', '.join(missing_packages)}",
                    "missing_packages": missing_packages,
                    "need_install": True,
                    "message": f"❌ 执行失败，需要安装以下包：{', '.join(missing_packages)}\n是否需要安装？请回复'是'或'安装'来确认。"
                }
            
            return {
                "success": False,
                "error": error[-1000:] if len(error) > 1000 else error,
                "output": output[-500:] if len(output) > 500 else output,
                "return_code": result.returncode
            }
            
    except subprocess.TimeoutExpired:
        logger.error(f"[Python] 执行超时")
        return {
            "success": False,
            "error": f"执行超时（超过 {timeout} 秒）"
        }
    except Exception as e:
        logger.error(f"[Python] 执行异常: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        # 清理临时脚本
        if temp_script and temp_script.exists():
            try:
                temp_script.unlink()
                logger.info(f"[Python] 已清理临时脚本: {temp_script.name}")
            except Exception as e:
                logger.warning(f"[Python] 清理临时脚本失败: {e}")


def _detect_missing_packages(error_message: str) -> List[str]:
    """
    从错误信息中检测缺失的包
    """
    import re
    
    missing = []
    
    # 匹配 ModuleNotFoundError: No module named 'xxx'
    pattern1 = r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]"
    matches = re.findall(pattern1, error_message)
    missing.extend(matches)
    
    # 匹配 ImportError: No module named xxx
    pattern2 = r"ImportError: No module named ['\"]?([^\s'\"]+)['\"]?"
    matches = re.findall(pattern2, error_message)
    missing.extend(matches)
    
    # 匹配 cannot import name 'xxx' from 'yyy'
    pattern3 = r"cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]"
    matches = re.findall(pattern3, error_message)
    for name, module in matches:
        if module not in missing:
            missing.append(module)
    
    # 转换导入名到包名
    import_to_package = {
        "pptx": "python-pptx",
        "PIL": "Pillow",
        "cv2": "opencv-python",
        "sklearn": "scikit-learn",
        "bs4": "beautifulsoup4",
        "yaml": "pyyaml",
    }
    
    result = []
    for m in missing:
        # 取顶级模块名
        top_module = m.split('.')[0]
        package_name = import_to_package.get(top_module, top_module)
        if package_name not in result:
            result.append(package_name)
    
    return result


def convert_file(
    input_path: str,
    output_format: str,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    文件格式转换（支持 txt->pptx 等）
    
    Args:
        input_path: 输入文件路径（相对于项目根目录）
        output_format: 目标格式（如 pptx, pdf, docx）
        output_path: 输出文件路径（可选，默认在同目录）
        
    Returns:
        转换结果
    """
    logger.info(f"[Python] 转换文件: {input_path} -> {output_format}")
    
    input_file = PROJECT_ROOT / input_path
    
    if not input_file.exists():
        return {
            "success": False,
            "error": f"输入文件不存在: {input_path}"
        }
    
    # 确定输出路径
    if output_path:
        output_file = PROJECT_ROOT / output_path
    else:
        output_file = input_file.with_suffix(f".{output_format}")
    
    # 根据转换类型生成代码
    input_suffix = input_file.suffix.lower()
    output_format = output_format.lower()
    
    if output_format == "pptx":
        # 检查 python-pptx 是否安装
        check_result = check_package_installed("python-pptx")
        if not check_result.get("installed"):
            return {
                "success": False,
                "need_install": True,
                "missing_packages": ["python-pptx"],
                "message": "❌ 需要安装 python-pptx 包才能转换为 PPT。\n是否安装？请回复'是'或'安装'来确认。"
            }
        
        # 生成转换代码
        code = _generate_txt_to_pptx_code(str(input_file), str(output_file))
        
    else:
        return {
            "success": False,
            "error": f"暂不支持转换为 {output_format} 格式"
        }
    
    # 执行转换
    result = execute_python_code(
        code=code,
        description=f"转换 {input_path} 为 {output_format}",
        working_directory=str(input_file.parent.relative_to(PROJECT_ROOT)) if input_file.parent != PROJECT_ROOT else None
    )
    
    if result.get("success"):
        result["output_file"] = str(output_file.relative_to(PROJECT_ROOT))
        result["message"] = f"✅ 文件转换成功！\n输出文件: {result['output_file']}"
    
    return result


def _generate_txt_to_pptx_code(input_path: str, output_path: str) -> str:
    """
    生成 txt 转 pptx 的 Python 代码
    """
    return f'''# 自动生成的 txt -> pptx 转换脚本
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RgbColor

# 读取文本文件
input_path = r"{input_path}"
output_path = r"{output_path}"

with open(input_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 创建 PPT
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

# 按段落分割内容
paragraphs = [p.strip() for p in content.split('\\n\\n') if p.strip()]

# 如果没有明确分段，按行分割
if len(paragraphs) <= 1:
    lines = [l.strip() for l in content.split('\\n') if l.strip()]
    # 每 5 行一页
    paragraphs = []
    for i in range(0, len(lines), 5):
        paragraphs.append('\\n'.join(lines[i:i+5]))

# 创建幻灯片
for i, para in enumerate(paragraphs):
    # 添加标题幻灯片或内容幻灯片
    if i == 0:
        slide_layout = prs.slide_layouts[0]  # 标题布局
        slide = prs.slides.add_slide(slide_layout)
        title = slide.shapes.title
        subtitle = slide.placeholders[1]
        
        lines = para.split('\\n')
        title.text = lines[0] if lines else "演示文稿"
        if len(lines) > 1:
            subtitle.text = '\\n'.join(lines[1:])
    else:
        slide_layout = prs.slide_layouts[1]  # 标题和内容布局
        slide = prs.slides.add_slide(slide_layout)
        title = slide.shapes.title
        content_shape = slide.placeholders[1]
        
        lines = para.split('\\n')
        title.text = f"第 {{i}} 页"
        content_shape.text = para

# 保存
prs.save(output_path)
print(f"PPT 已保存到: {{output_path}}")
'''


# ============== 工具定义 ==============

CHECK_PACKAGE_TOOL = ToolDefinition(
    name="check_package",
    description="检查 Python 包是否已安装",
    parameters=[
        ToolParameter(
            name="package_name",
            type=ParameterType.STRING,
            description="要检查的包名称（如 python-pptx, pandas, numpy）",
            required=True
        )
    ],
    handler=check_package_installed,
    category="python"
)

INSTALL_PACKAGE_TOOL = ToolDefinition(
    name="install_package",
    description="安装 Python 包。用户确认后才能调用此工具",
    parameters=[
        ToolParameter(
            name="package_name",
            type=ParameterType.STRING,
            description="要安装的包名称",
            required=True
        ),
        ToolParameter(
            name="upgrade",
            type=ParameterType.BOOLEAN,
            description="是否升级已安装的包",
            required=False,
            default=False
        )
    ],
    handler=install_python_package,
    category="python"
)

EXECUTE_PYTHON_TOOL = ToolDefinition(
    name="execute_python",
    description="执行 Python 代码。会创建临时脚本，执行后自动删除",
    parameters=[
        ToolParameter(
            name="code",
            type=ParameterType.STRING,
            description="要执行的 Python 代码",
            required=True
        ),
        ToolParameter(
            name="description",
            type=ParameterType.STRING,
            description="代码功能描述",
            required=False,
            default=""
        ),
        ToolParameter(
            name="working_directory",
            type=ParameterType.STRING,
            description="工作目录（相对于项目根目录）",
            required=False,
            default=""
        ),
        ToolParameter(
            name="timeout",
            type=ParameterType.INTEGER,
            description="执行超时时间（秒），默认60秒",
            required=False,
            default=60
        )
    ],
    handler=execute_python_code,
    category="python"
)

CONVERT_FILE_TOOL = ToolDefinition(
    name="convert_file",
    description="文件格式转换，如 txt 转 pptx。会自动检查并提示安装所需的包",
    parameters=[
        ToolParameter(
            name="input_path",
            type=ParameterType.STRING,
            description="输入文件路径（相对于项目根目录）",
            required=True
        ),
        ToolParameter(
            name="output_format",
            type=ParameterType.STRING,
            description="目标格式（如 pptx, pdf, docx）",
            required=True
        ),
        ToolParameter(
            name="output_path",
            type=ParameterType.STRING,
            description="输出文件路径（可选，默认在同目录）",
            required=False
        )
    ],
    handler=convert_file,
    category="python"
)


# 导出所有 Python 工具
PYTHON_TOOLS = [
    CHECK_PACKAGE_TOOL,
    INSTALL_PACKAGE_TOOL,
    EXECUTE_PYTHON_TOOL,
    CONVERT_FILE_TOOL
]


def get_python_tools() -> List[ToolDefinition]:
    """获取所有 Python 工具"""
    return PYTHON_TOOLS
