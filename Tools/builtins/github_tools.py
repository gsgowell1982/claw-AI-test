"""
GitHub Tools - GitHub 操作工具

版本: v2.3.2
更新:
- 修复异步执行问题
- 使用同步 HTTP 请求确保稳定性
- 改进错误处理

提供:
- 设置/验证 Token
- 创建仓库
- 列出仓库
- 获取仓库信息
"""

import os
import urllib.request
import urllib.error
import json
import ssl
from typing import Optional, List, Dict, Any

from ..schema import ToolDefinition, ToolParameter, ParameterType

import logging
logger = logging.getLogger("OpenClaw.GitHub")


# GitHub API 配置
GITHUB_API_BASE = "https://api.github.com"

# 会话级 Token 存储
_session_token: Optional[str] = None


def set_github_token(token: str) -> None:
    """设置会话级 GitHub Token"""
    global _session_token
    _session_token = token
    logger.info(f"[GitHub] Token 已设置 (长度: {len(token)})")


def get_github_token() -> Optional[str]:
    """获取 GitHub Token（优先使用会话 Token）"""
    global _session_token
    return _session_token or os.environ.get("GITHUB_TOKEN")


def clear_github_token() -> None:
    """清除会话级 Token"""
    global _session_token
    _session_token = None


def _make_github_request(
    method: str,
    endpoint: str,
    data: Optional[Dict] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    发起 GitHub API 请求 (同步版本)
    """
    use_token = token or get_github_token()
    
    if not use_token:
        return {
            "success": False,
            "error": "未配置 GitHub Token。请提供您的 GitHub Personal Access Token。\n\n获取方式：\n1. 访问 https://github.com/settings/tokens\n2. 点击 'Generate new token (classic)'\n3. 选择 repo 权限\n4. 生成并复制 Token（以 ghp_ 开头）",
            "need_token": True
        }
    
    url = f"{GITHUB_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"token {use_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "OpenClaw-Agent",
        "Content-Type": "application/json"
    }
    
    logger.info(f"[GitHub] 请求: {method} {endpoint}")
    
    try:
        # 准备请求数据
        request_data = None
        if data:
            request_data = json.dumps(data).encode('utf-8')
        
        # 创建请求
        req = urllib.request.Request(url, data=request_data, headers=headers, method=method)
        
        # 创建 SSL 上下文
        ctx = ssl.create_default_context()
        
        # 发送请求
        with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
            status = response.status
            response_data = response.read().decode('utf-8')
            
            logger.info(f"[GitHub] 响应状态: {status}")
            
            if response_data:
                result = json.loads(response_data)
            else:
                result = {}
            
            return {"success": True, "data": result, "status": status}
    
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            error_body = e.read().decode('utf-8')
            error_data = json.loads(error_body)
            error_msg = error_data.get("message", str(error_data))
        except:
            error_msg = str(e)
        
        logger.error(f"[GitHub] HTTP 错误 {status}: {error_msg}")
        
        if status == 401:
            return {
                "success": False,
                "error": f"GitHub Token 无效或已过期。请检查您的 Token 是否正确。\n错误详情: {error_msg}",
                "status": status,
                "need_token": True
            }
        elif status == 422:
            if "already exists" in error_msg.lower():
                return {
                    "success": False,
                    "error": f"仓库名称已存在，请使用其他名称。",
                    "status": status
                }
            return {
                "success": False,
                "error": f"请求参数错误: {error_msg}",
                "status": status
            }
        elif status == 404:
            return {
                "success": False,
                "error": f"资源不存在: {error_msg}",
                "status": status
            }
        else:
            return {
                "success": False,
                "error": f"GitHub API 错误 ({status}): {error_msg}",
                "status": status
            }
    
    except urllib.error.URLError as e:
        logger.error(f"[GitHub] 网络错误: {e.reason}")
        return {
            "success": False,
            "error": f"网络连接失败: {e.reason}。请检查网络连接。"
        }
    
    except Exception as e:
        logger.error(f"[GitHub] 异常: {str(e)}")
        return {
            "success": False,
            "error": f"请求异常: {str(e)}"
        }


def github_set_token(token: str) -> Dict[str, Any]:
    """
    设置并验证 GitHub Token
    
    Args:
        token: GitHub Personal Access Token (以 ghp_ 开头)
        
    Returns:
        设置结果
    """
    logger.info(f"[GitHub] 验证 Token...")
    
    if not token or len(token) < 10:
        return {
            "success": False,
            "error": "Token 格式不正确，请提供有效的 GitHub Personal Access Token（以 ghp_ 开头）。"
        }
    
    # 先设置 Token
    set_github_token(token)
    
    # 验证 Token
    result = _make_github_request("GET", "/user")
    
    if result.get("success"):
        user_data = result.get("data", {})
        logger.info(f"[GitHub] Token 验证成功，用户: {user_data.get('login')}")
        return {
            "success": True,
            "message": f"✅ GitHub Token 验证成功！已登录为: {user_data.get('login')}",
            "user": {
                "login": user_data.get("login"),
                "name": user_data.get("name"),
                "url": user_data.get("html_url"),
                "public_repos": user_data.get("public_repos")
            }
        }
    else:
        # 验证失败，清除 Token
        clear_github_token()
        logger.error(f"[GitHub] Token 验证失败: {result.get('error')}")
        return result


def github_create_repo(
    name: str,
    description: str = "",
    private: bool = False
) -> Dict[str, Any]:
    """
    在 GitHub 上创建新仓库
    
    Args:
        name: 仓库名称
        description: 仓库描述
        private: 是否私有
        
    Returns:
        创建结果
    """
    logger.info(f"[GitHub] 创建仓库: {name}")
    
    data = {
        "name": name,
        "description": description or f"Created by OpenClaw Agent",
        "private": private,
        "auto_init": True
    }
    
    result = _make_github_request("POST", "/user/repos", data)
    
    if result.get("success"):
        repo_data = result.get("data", {})
        logger.info(f"[GitHub] 仓库创建成功: {repo_data.get('full_name')}")
        return {
            "success": True,
            "message": f"✅ 仓库创建成功！",
            "repo": {
                "name": repo_data.get("name"),
                "full_name": repo_data.get("full_name"),
                "url": repo_data.get("html_url"),
                "clone_url": repo_data.get("clone_url"),
                "private": repo_data.get("private")
            }
        }
    
    return result


def github_list_repos(username: Optional[str] = None) -> Dict[str, Any]:
    """
    列出 GitHub 仓库
    
    Args:
        username: 用户名，不提供则列出当前用户的仓库
        
    Returns:
        仓库列表
    """
    if username:
        endpoint = f"/users/{username}/repos?sort=updated&per_page=20"
    else:
        endpoint = "/user/repos?sort=updated&per_page=20"
    
    logger.info(f"[GitHub] 列出仓库: {endpoint}")
    
    result = _make_github_request("GET", endpoint)
    
    if result.get("success"):
        repos = result.get("data", [])
        return {
            "success": True,
            "count": len(repos),
            "repos": [
                {
                    "name": r.get("name"),
                    "full_name": r.get("full_name"),
                    "url": r.get("html_url"),
                    "description": r.get("description") or "",
                    "private": r.get("private"),
                    "stars": r.get("stargazers_count", 0)
                }
                for r in repos
            ]
        }
    
    return result


def github_get_repo(owner: str, repo: str) -> Dict[str, Any]:
    """
    获取 GitHub 仓库信息
    
    Args:
        owner: 仓库所有者
        repo: 仓库名称
        
    Returns:
        仓库信息
    """
    logger.info(f"[GitHub] 获取仓库: {owner}/{repo}")
    
    result = _make_github_request("GET", f"/repos/{owner}/{repo}")
    
    if result.get("success"):
        r = result.get("data", {})
        return {
            "success": True,
            "repo": {
                "name": r.get("name"),
                "full_name": r.get("full_name"),
                "url": r.get("html_url"),
                "description": r.get("description") or "",
                "private": r.get("private"),
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "language": r.get("language"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at")
            }
        }
    
    return result


# ============== 工具定义 ==============

GITHUB_SET_TOKEN_TOOL = ToolDefinition(
    name="github_set_token",
    description="设置并验证 GitHub Token。在执行创建仓库等操作前，必须先调用此工具设置用户提供的 Token",
    parameters=[
        ToolParameter(
            name="token",
            type=ParameterType.STRING,
            description="用户提供的 GitHub Personal Access Token（以 ghp_ 开头的字符串）",
            required=True
        )
    ],
    handler=github_set_token,
    category="github"
)

GITHUB_CREATE_REPO_TOOL = ToolDefinition(
    name="github_create_repo",
    description="在 GitHub 上创建新仓库。注意：需要先使用 github_set_token 设置有效的 Token",
    parameters=[
        ToolParameter(
            name="name",
            type=ParameterType.STRING,
            description="仓库名称（如 my-project，不含空格）",
            required=True
        ),
        ToolParameter(
            name="description",
            type=ParameterType.STRING,
            description="仓库描述",
            required=False,
            default=""
        ),
        ToolParameter(
            name="private",
            type=ParameterType.BOOLEAN,
            description="是否为私有仓库，默认为公开",
            required=False,
            default=False
        )
    ],
    handler=github_create_repo,
    category="github"
)

GITHUB_LIST_REPOS_TOOL = ToolDefinition(
    name="github_list_repos",
    description="列出 GitHub 用户的仓库列表",
    parameters=[
        ToolParameter(
            name="username",
            type=ParameterType.STRING,
            description="GitHub 用户名。不提供则列出当前 Token 对应用户的仓库",
            required=False
        )
    ],
    handler=github_list_repos,
    category="github"
)

GITHUB_GET_REPO_TOOL = ToolDefinition(
    name="github_get_repo",
    description="获取 GitHub 仓库的详细信息",
    parameters=[
        ToolParameter(
            name="owner",
            type=ParameterType.STRING,
            description="仓库所有者的用户名",
            required=True
        ),
        ToolParameter(
            name="repo",
            type=ParameterType.STRING,
            description="仓库名称",
            required=True
        )
    ],
    handler=github_get_repo,
    category="github"
)


# 导出所有 GitHub 工具
GITHUB_TOOLS = [
    GITHUB_SET_TOKEN_TOOL,
    GITHUB_CREATE_REPO_TOOL,
    GITHUB_LIST_REPOS_TOOL,
    GITHUB_GET_REPO_TOOL
]


def get_github_tools() -> List[ToolDefinition]:
    """获取所有 GitHub 工具"""
    return GITHUB_TOOLS
