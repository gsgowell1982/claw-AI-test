"""
GitHub Tools - GitHub 操作工具

版本: v2.3.1
更新:
- 支持用户通过对话提供 GitHub Token
- 改进错误信息提示
- 添加 Token 验证

提供:
- 创建仓库
- 列出仓库
- 获取仓库信息
"""

import os
import aiohttp
import asyncio
from typing import Optional, List, Dict, Any

from ..schema import ToolDefinition, ToolParameter, ParameterType


# GitHub API 配置
GITHUB_API_BASE = "https://api.github.com"

# 会话级 Token 存储
_session_token: Optional[str] = None


def set_github_token(token: str) -> None:
    """设置会话级 GitHub Token"""
    global _session_token
    _session_token = token


def get_github_token() -> Optional[str]:
    """获取 GitHub Token（优先使用会话 Token）"""
    global _session_token
    return _session_token or os.environ.get("GITHUB_TOKEN")


def clear_github_token() -> None:
    """清除会话级 Token"""
    global _session_token
    _session_token = None


async def _make_github_request(
    method: str,
    endpoint: str,
    data: Optional[Dict] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """发起 GitHub API 请求"""
    # 获取 Token
    use_token = token or get_github_token()
    
    if not use_token:
        return {
            "success": False,
            "error": "未配置 GitHub Token。请提供您的 GitHub Personal Access Token。\n\n获取方式：\n1. 访问 https://github.com/settings/tokens\n2. 点击 'Generate new token'\n3. 选择所需权限（至少需要 repo 权限）\n4. 复制生成的 Token\n\n然后告诉我您的 Token，或设置环境变量：\nexport GITHUB_TOKEN=your_token_here",
            "need_token": True
        }
    
    headers = {
        "Authorization": f"token {use_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "OpenClaw-Agent"
    }
    
    url = f"{GITHUB_API_BASE}{endpoint}"
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if method.upper() == "GET":
                async with session.get(url, headers=headers) as response:
                    result = await response.json()
                    if response.status == 401:
                        return {
                            "success": False,
                            "error": "GitHub Token 无效或已过期。请检查您的 Token 是否正确。",
                            "status": response.status,
                            "need_token": True
                        }
                    if response.status >= 400:
                        error_msg = result.get("message", str(result))
                        return {
                            "success": False,
                            "error": f"GitHub API 错误: {error_msg}",
                            "status": response.status
                        }
                    return {"success": True, "data": result, "status": response.status}
            
            elif method.upper() == "POST":
                async with session.post(url, headers=headers, json=data) as response:
                    result = await response.json()
                    if response.status == 401:
                        return {
                            "success": False,
                            "error": "GitHub Token 无效或已过期。请检查您的 Token 是否正确。",
                            "status": response.status,
                            "need_token": True
                        }
                    if response.status == 422:
                        errors = result.get("errors", [])
                        if errors and errors[0].get("message") == "name already exists on this account":
                            return {
                                "success": False,
                                "error": f"仓库名称 '{data.get('name')}' 已存在，请使用其他名称。",
                                "status": response.status
                            }
                        return {
                            "success": False,
                            "error": f"请求参数错误: {result.get('message', str(result))}",
                            "status": response.status
                        }
                    if response.status >= 400:
                        return {
                            "success": False,
                            "error": f"GitHub API 错误: {result.get('message', str(result))}",
                            "status": response.status
                        }
                    return {"success": True, "data": result, "status": response.status}
            
            elif method.upper() == "DELETE":
                async with session.delete(url, headers=headers) as response:
                    if response.status == 204:
                        return {"success": True, "message": "删除成功", "status": response.status}
                    if response.status == 401:
                        return {
                            "success": False,
                            "error": "GitHub Token 无效或已过期。",
                            "status": response.status,
                            "need_token": True
                        }
                    result = await response.json()
                    return {
                        "success": False,
                        "error": f"删除失败: {result.get('message', str(result))}",
                        "status": response.status
                    }
    
    except aiohttp.ClientConnectorError:
        return {"success": False, "error": "网络连接失败，请检查网络连接。"}
    except asyncio.TimeoutError:
        return {"success": False, "error": "请求超时，请稍后重试。"}
    except Exception as e:
        return {"success": False, "error": f"请求异常: {str(e)}"}


def _run_async(coro):
    """运行异步函数"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def github_create_repo(
    name: str,
    description: str = "",
    private: bool = False,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    在 GitHub 上创建新仓库
    
    Args:
        name: 仓库名称
        description: 仓库描述
        private: 是否私有
        token: GitHub Token (可选，如果之前已提供则不需要)
        
    Returns:
        创建结果
    """
    # 如果提供了新 Token，保存它
    if token:
        set_github_token(token)
    
    async def _create():
        data = {
            "name": name,
            "description": description or f"Created by OpenClaw Agent",
            "private": private,
            "auto_init": True
        }
        
        result = await _make_github_request("POST", "/user/repos", data)
        
        if result.get("success"):
            repo_data = result.get("data", {})
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
    
    return _run_async(_create())


def github_list_repos(
    username: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    列出 GitHub 仓库
    
    Args:
        username: 用户名，不提供则列出当前用户的仓库
        token: GitHub Token (可选)
        
    Returns:
        仓库列表
    """
    if token:
        set_github_token(token)
    
    async def _list():
        if username:
            endpoint = f"/users/{username}/repos?sort=updated&per_page=20"
        else:
            endpoint = "/user/repos?sort=updated&per_page=20"
        
        result = await _make_github_request("GET", endpoint)
        
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
    
    return _run_async(_list())


def github_get_repo(
    owner: str,
    repo: str,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取 GitHub 仓库信息
    
    Args:
        owner: 仓库所有者
        repo: 仓库名称
        token: GitHub Token (可选)
        
    Returns:
        仓库信息
    """
    if token:
        set_github_token(token)
    
    async def _get():
        result = await _make_github_request("GET", f"/repos/{owner}/{repo}")
        
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
    
    return _run_async(_get())


def github_set_token(token: str) -> Dict[str, Any]:
    """
    设置 GitHub Token
    
    Args:
        token: GitHub Personal Access Token
        
    Returns:
        设置结果
    """
    if not token or len(token) < 10:
        return {
            "success": False,
            "error": "Token 格式不正确，请提供有效的 GitHub Personal Access Token。"
        }
    
    # 验证 Token
    async def _verify():
        set_github_token(token)
        result = await _make_github_request("GET", "/user")
        
        if result.get("success"):
            user_data = result.get("data", {})
            return {
                "success": True,
                "message": f"✅ GitHub Token 验证成功！已登录为: {user_data.get('login')}",
                "user": {
                    "login": user_data.get("login"),
                    "name": user_data.get("name"),
                    "url": user_data.get("html_url")
                }
            }
        else:
            clear_github_token()
            return {
                "success": False,
                "error": "Token 验证失败: " + result.get("error", "未知错误")
            }
    
    return _run_async(_verify())


# ============== 工具定义 ==============

GITHUB_SET_TOKEN_TOOL = ToolDefinition(
    name="github_set_token",
    description="设置并验证 GitHub Token（在执行其他 GitHub 操作前需要先设置）",
    parameters=[
        ToolParameter(
            name="token",
            type=ParameterType.STRING,
            description="GitHub Personal Access Token（以 ghp_ 开头）",
            required=True
        )
    ],
    handler=github_set_token,
    category="github"
)

GITHUB_CREATE_REPO_TOOL = ToolDefinition(
    name="github_create_repo",
    description="在 GitHub 上创建新仓库（需要先设置 Token）",
    parameters=[
        ToolParameter(
            name="name",
            type=ParameterType.STRING,
            description="仓库名称（如 my-project）",
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
            description="是否为私有仓库",
            required=False,
            default=False
        )
    ],
    handler=github_create_repo,
    category="github"
)

GITHUB_LIST_REPOS_TOOL = ToolDefinition(
    name="github_list_repos",
    description="列出 GitHub 用户的仓库",
    parameters=[
        ToolParameter(
            name="username",
            type=ParameterType.STRING,
            description="GitHub 用户名，不提供则列出当前认证用户的仓库",
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
            description="仓库所有者用户名",
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
