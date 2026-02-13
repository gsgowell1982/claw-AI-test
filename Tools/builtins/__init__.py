# Tools Builtins - 内置工具
"""
内置工具实现 v2.5.2

包含:
- 文件操作工具 (list_files, read_file, write_file)
- GitHub 工具 (create_repo, list_repos, get_repo, create_release, delete_repo)
- Python 工具 (check_package, analyze_packages, install_package, execute_python, convert_file)

v2.5.2 更新:
- 新增 analyze_packages 工具：根据用户意图分析所需包
- 改进错误检测：区分"包未安装"和"代码导入错误"
- 修复 pptx 生成代码中的 RgbColor 导入错误
"""

from .file_tools import get_file_tools, FILE_TOOLS
from .github_tools import get_github_tools, GITHUB_TOOLS
from .python_tools import (
    get_python_tools, 
    PYTHON_TOOLS,
    check_package_installed,
    analyze_required_packages,
    install_python_package,
    execute_python_code,
    convert_file
)

__all__ = [
    'get_file_tools',
    'FILE_TOOLS',
    'get_github_tools', 
    'GITHUB_TOOLS',
    'get_python_tools',
    'PYTHON_TOOLS',
    # 直接导出的函数
    'check_package_installed',
    'analyze_required_packages',
    'install_python_package',
    'execute_python_code',
    'convert_file'
]
