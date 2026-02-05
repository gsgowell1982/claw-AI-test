"""
GitHub Tools - GitHub 操作工具

版本: v2.3
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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


async def _make_github_request(
    method: str,
    endpoint: str,
    data: Optional[Dict] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """发起 GitHub API 请求"""
    token = token or GITHUB_TOKEN
    
    if not token:
        return {
            "success": False,
            "error": "未配置 GitHub Token。请设置环境变量 GITHUB_TOKEN"
        }
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "OpenClaw-Agent"
    }
    
    url = f"{GITHUB_API_BASE}{endpoint}"
    
    try:
        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(url, headers=headers) as response:
                    result = await response.json()
                    if response.status >= 400:
                        return {"success": False, "error": result.get("message", str(result)), "status": response.status}
                    return {"success": True, "data": result, "status": response.status}
            
            elif method.upper() == "POST":
                async with session.post(url, headers=headers, json=data) as response:
                    result = await response.json()
                    if response.status >= 400:
                        return {"success": False, "error": result.get("message", str(result)), "status": response.status}
                    return {"success": True, "data": result, "status": response.status}
            
            elif method.upper() == "DELETE":
                async with session.delete(url, headers=headers) as response:
                    if response.status == 204:
                        return {"success": True, "message": "删除成功", "status": response.status}
                    result = await response.json()
                    if response.status >= 400:
                        return {"success": False, "error": result.get("message", str(result)), "status": response.status}
                    return {"success": True, "data": result, "status": response.status}
    
    except aiohttp.ClientError as e:
        return {"success": False, "error": f"网络请求失败: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"请求异常: {str(e)}"}


def _run_async(coro):
    """运行异步函数"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果已有事件循环在运行，创建新任务
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


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
    async def _create():
        data = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": True  # 自动初始化 README
        }
        
        result = await _make_github_request("POST", "/user/repos", data)
        
        if result.get("success"):
            repo_data = result.get("data", {})
            return {
                "success": True,
                "message": f"仓库创建成功: {repo_data.get('full_name')}",
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


def github_list_repos(username: Optional[str] = None) -> Dict[str, Any]:
    """
    列出 GitHub 仓库
    
    Args:
        username: 用户名，不提供则列出当前用户的仓库
        
    Returns:
        仓库列表
    """
    async def _list():
        if username:
            endpoint = f"/users/{username}/repos"
        else:
            endpoint = "/user/repos"
        
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
                        "description": r.get("description"),
                        "private": r.get("private"),
                        "stars": r.get("stargazers_count", 0)
                    }
                    for r in repos[:20]  # 限制返回数量
                ]
            }
        return result
    
    return _run_async(_list())


def github_get_repo(owner: str, repo: str) -> Dict[str, Any]:
    """
    获取 GitHub 仓库信息
    
    Args:
        owner: 仓库所有者
        repo: 仓库名称
        
    Returns:
        仓库信息
    """
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
                    "description": r.get("description"),
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


# ============== 工具定义 ==============

GITHUB_CREATE_REPO_TOOL = ToolDefinition(
    name="github_create_repo",
    description="在 GitHub 上创建新仓库",
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
GITHUB_TOOLS = [GITHUB_CREATE_REPO_TOOL, GITHUB_LIST_REPOS_TOOL, GITHUB_GET_REPO_TOOL]


def get_github_tools() -> List[ToolDefinition]:
    """获取所有 GitHub 工具"""
    return GITHUB_TOOLS
