"""
Tool Runtime v2.3 - 工具执行运行时

版本: v2.3
负责:
- 工具注册与管理
- 解析 LLM 的 tool_calls
- 执行工具函数
- 结果回传给 LLM
"""

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import json
import re
import logging

from Tools.schema import ToolDefinition, generate_tools_prompt
from Tools.builtins.file_tools import get_file_tools
from Tools.builtins.github_tools import get_github_tools

logger = logging.getLogger("OpenClaw.Runtime")


@dataclass
class ToolCall:
    """工具调用"""
    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time_ms: float = 0
    
    def to_message(self) -> Dict[str, Any]:
        """转换为消息格式"""
        if self.success:
            content = json.dumps(self.result, ensure_ascii=False, indent=2)
        else:
            content = f"工具执行失败: {self.error}"
        
        return {
            "role": "tool",
            "name": self.tool_name,
            "content": content
        }


class ToolRuntime:
    """
    工具运行时 v2.3
    
    管理工具的注册、调用和结果处理
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._execution_history: List[Dict[str, Any]] = []
        
        # 加载内置工具
        self._load_builtin_tools()
    
    def _load_builtin_tools(self):
        """加载内置工具"""
        # 文件工具
        for tool in get_file_tools():
            self.register_tool(tool)
            logger.info(f"[Runtime] 注册工具: {tool.name} ({tool.category})")
        
        # GitHub 工具
        for tool in get_github_tools():
            self.register_tool(tool)
            logger.info(f"[Runtime] 注册工具: {tool.name} ({tool.category})")
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
    
    def unregister_tool(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[ToolDefinition]:
        """列出所有工具"""
        return list(self._tools.values())
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """获取所有工具的 JSON Schema"""
        return [tool.to_schema() for tool in self._tools.values()]
    
    def get_system_prompt(self) -> str:
        """获取包含工具描述的 System Prompt"""
        return generate_tools_prompt(list(self._tools.values()))
    
    def parse_tool_calls(self, content: str) -> List[ToolCall]:
        """
        从 LLM 响应中解析工具调用
        
        支持多种格式:
        1. JSON 格式: {"tool_calls": [{"name": "xxx", "arguments": {...}}]}
        2. 代码块格式: ```json {...} ```
        
        Args:
            content: LLM 响应内容
            
        Returns:
            工具调用列表
        """
        tool_calls = []
        
        logger.debug(f"[Runtime] 开始解析工具调用，内容长度: {len(content)}")
        
        # 方法1: 尝试提取代码块中的 JSON
        code_block_patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # ```json {...} ```
            r'```\s*([\s\S]*?)\s*```',       # ``` {...} ```
        ]
        
        for pattern in code_block_patterns:
            matches = re.findall(pattern, content)
            logger.debug(f"[Runtime] 代码块模式匹配数: {len(matches)}")
            for match in matches:
                parsed = self._try_parse_tool_json(match.strip())
                if parsed:
                    logger.info(f"[Runtime] 从代码块解析到 {len(parsed)} 个工具调用")
                    tool_calls.extend(parsed)
                    return tool_calls
        
        # 方法2: 尝试查找内联的 JSON 对象 (使用括号匹配)
        json_objects = self._extract_json_objects(content)
        logger.debug(f"[Runtime] 提取到 {len(json_objects)} 个 JSON 对象")
        
        for json_str in json_objects:
            logger.debug(f"[Runtime] 尝试解析 JSON: {json_str[:100]}...")
            parsed = self._try_parse_tool_json(json_str)
            if parsed:
                logger.info(f"[Runtime] 从内联 JSON 解析到 {len(parsed)} 个工具调用")
                tool_calls.extend(parsed)
                return tool_calls
        
        # 方法3: 最后尝试使用正则直接提取 (备用方案)
        if "tool_calls" in content and not tool_calls:
            logger.warning(f"[Runtime] 标准解析失败，尝试正则备用方案")
            tool_calls = self._regex_fallback_parse(content)
            if tool_calls:
                logger.info(f"[Runtime] 正则备用方案解析到 {len(tool_calls)} 个工具调用")
        
        if "tool_calls" in content and not tool_calls:
            logger.warning(f"[Runtime] 所有解析方案均失败")
        
        return tool_calls
    
    def _regex_fallback_parse(self, content: str) -> List[ToolCall]:
        """
        使用正则表达式作为备用解析方案
        针对 write_file 等包含代码内容的工具调用
        """
        tool_calls = []
        
        # 匹配 write_file 工具调用
        # 格式: {"name": "write_file", "arguments": {"filename": "xxx", "content": "..."}}
        write_file_pattern = r'"name"\s*:\s*"write_file"\s*,\s*"arguments"\s*:\s*\{\s*"filename"\s*:\s*"([^"]+)"'
        match = re.search(write_file_pattern, content)
        
        if match:
            filename = match.group(1)
            
            # 尝试提取 content 字段
            # 找到 "content": " 之后的内容，直到找到结束的引号和大括号
            content_start = content.find('"content"', match.end())
            if content_start > 0:
                # 找到 "content": " 后的实际内容起始位置
                quote_pos = content.find('"', content_start + len('"content"') + 1)
                if quote_pos > 0:
                    # 从这里开始找结束引号（需要处理转义）
                    file_content = self._extract_string_value(content, quote_pos)
                    if file_content is not None:
                        tool_calls.append(ToolCall(
                            name="write_file",
                            arguments={"filename": filename, "content": file_content}
                        ))
                        return tool_calls
        
        # 匹配 list_files 工具调用
        list_files_pattern = r'"name"\s*:\s*"list_files"\s*,\s*"arguments"\s*:\s*\{([^}]*)\}'
        match = re.search(list_files_pattern, content)
        if match:
            args_str = match.group(1).strip()
            arguments = {}
            if args_str:
                # 提取 path 参数
                path_match = re.search(r'"path"\s*:\s*"([^"]*)"', args_str)
                if path_match:
                    arguments["path"] = path_match.group(1)
            tool_calls.append(ToolCall(name="list_files", arguments=arguments))
            return tool_calls
        
        # 匹配 read_file 工具调用
        read_file_pattern = r'"name"\s*:\s*"read_file"\s*,\s*"arguments"\s*:\s*\{\s*"path"\s*:\s*"([^"]+)"'
        match = re.search(read_file_pattern, content)
        if match:
            tool_calls.append(ToolCall(
                name="read_file",
                arguments={"path": match.group(1)}
            ))
            return tool_calls
        
        return tool_calls
    
    def _extract_string_value(self, text: str, start_quote_pos: int) -> Optional[str]:
        """
        从 JSON 字符串中提取值，处理转义字符
        start_quote_pos 是开始引号的位置
        """
        result = []
        i = start_quote_pos + 1  # 跳过开始引号
        escape = False
        
        while i < len(text):
            char = text[i]
            
            if escape:
                # 处理转义字符
                if char == 'n':
                    result.append('\n')
                elif char == 't':
                    result.append('\t')
                elif char == 'r':
                    result.append('\r')
                elif char == '"':
                    result.append('"')
                elif char == '\\':
                    result.append('\\')
                else:
                    result.append(char)
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                # 找到结束引号
                return ''.join(result)
            else:
                result.append(char)
            
            i += 1
        
        # 如果没有找到结束引号，返回已收集的内容
        if result:
            logger.warning(f"[Runtime] 字符串值可能被截断，长度: {len(result)}")
            return ''.join(result)
        
        return None
    
    def _extract_json_objects(self, text: str) -> List[str]:
        """
        从文本中提取完整的 JSON 对象（处理嵌套大括号）
        """
        results = []
        i = 0
        while i < len(text):
            if text[i] == '{':
                # 找到一个 { ，尝试匹配完整的 JSON
                start = i
                depth = 0
                in_string = False
                escape = False
                
                j = i
                while j < len(text):
                    char = text[j]
                    
                    if escape:
                        escape = False
                        j += 1
                        continue
                    
                    if char == '\\':
                        escape = True
                        j += 1
                        continue
                    
                    if char == '"':
                        in_string = not in_string
                        j += 1
                        continue
                    
                    if not in_string:
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                # 找到完整的 JSON 对象
                                json_str = text[start:j+1]
                                results.append(json_str)
                                break
                    j += 1
                
                # 如果没有找到匹配的结束括号，跳过这个起始括号
                if depth != 0:
                    logger.debug(f"[Runtime] JSON 括号不匹配，depth={depth}，可能被截断")
                    # 尝试提取部分 JSON 用于修复
                    partial_json = text[start:]
                    if '"tool_calls"' in partial_json and partial_json not in results:
                        results.append(partial_json)
                
                i = j + 1
            else:
                i += 1
        
        return results
    
    def _try_parse_tool_json(self, json_str: str) -> List[ToolCall]:
        """
        尝试将字符串解析为工具调用
        """
        tool_calls = []
        try:
            data = json.loads(json_str)
            
            # 处理 tool_calls 数组
            if isinstance(data, dict) and "tool_calls" in data:
                for tc in data["tool_calls"]:
                    if isinstance(tc, dict) and "name" in tc:
                        tool_calls.append(ToolCall(
                            name=tc.get("name", ""),
                            arguments=tc.get("arguments", {}),
                            id=tc.get("id")
                        ))
            # 处理单个工具调用
            elif isinstance(data, dict) and "name" in data:
                tool_calls.append(ToolCall(
                    name=data.get("name", ""),
                    arguments=data.get("arguments", {}),
                    id=data.get("id")
                ))
        except json.JSONDecodeError as e:
            # 记录解析错误
            logger.warning(f"[Runtime] JSON 解析失败: {e}")
            logger.debug(f"[Runtime] 失败的 JSON 字符串 (前500字符): {json_str[:500]}")
            
            # 尝试修复常见问题后重试
            fixed_json = self._try_fix_json(json_str)
            if fixed_json and fixed_json != json_str:
                logger.info("[Runtime] 尝试修复后的 JSON...")
                return self._try_parse_tool_json(fixed_json)
        
        return tool_calls
    
    def _try_fix_json(self, json_str: str) -> Optional[str]:
        """
        尝试修复常见的 JSON 问题
        """
        import re
        
        # 1. 如果 JSON 被截断，尝试找到最后一个完整的对象
        # 查找 tool_calls 数组的结束
        if '"tool_calls"' in json_str:
            # 尝试找到 arguments 对象的结束位置
            # 查找模式: "arguments": {...}
            match = re.search(r'"arguments"\s*:\s*\{', json_str)
            if match:
                start = match.end() - 1  # { 的位置
                depth = 0
                end = -1
                in_string = False
                escape = False
                
                for i in range(start, len(json_str)):
                    char = json_str[i]
                    if escape:
                        escape = False
                        continue
                    if char == '\\':
                        escape = True
                        continue
                    if char == '"':
                        in_string = not in_string
                        continue
                    if not in_string:
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                end = i
                                break
                
                if end > 0:
                    # 构建完整的 JSON
                    # 提取 name 和 arguments
                    name_match = re.search(r'"name"\s*:\s*"([^"]+)"', json_str)
                    if name_match:
                        name = name_match.group(1)
                        arguments_str = json_str[start:end+1]
                        try:
                            arguments = json.loads(arguments_str)
                            fixed = json.dumps({
                                "tool_calls": [{
                                    "name": name,
                                    "arguments": arguments
                                }]
                            })
                            return fixed
                        except:
                            pass
        
        return None
    
    def has_tool_calls(self, content: str) -> bool:
        """检查响应是否包含工具调用"""
        return len(self.parse_tool_calls(content)) > 0
    
    async def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        执行单个工具调用
        
        Args:
            tool_call: 工具调用
            
        Returns:
            执行结果
        """
        start_time = datetime.now()
        
        tool = self._tools.get(tool_call.name)
        if not tool:
            return ToolResult(
                tool_name=tool_call.name,
                success=False,
                result=None,
                error=f"工具不存在: {tool_call.name}"
            )
        
        if not tool.handler:
            return ToolResult(
                tool_name=tool_call.name,
                success=False,
                result=None,
                error=f"工具未实现: {tool_call.name}"
            )
        
        try:
            logger.info(f"[Runtime] 执行工具: {tool_call.name}, 参数: {tool_call.arguments}")
            
            # 执行工具
            if tool.is_async:
                result = await tool.handler(**tool_call.arguments)
            else:
                result = tool.handler(**tool_call.arguments)
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(f"[Runtime] 工具执行完成: {tool_call.name}, 耗时: {execution_time:.0f}ms")
            
            # 记录历史
            self._execution_history.append({
                "tool": tool_call.name,
                "arguments": tool_call.arguments,
                "result": result,
                "timestamp": datetime.now().isoformat(),
                "execution_time_ms": execution_time
            })
            
            return ToolResult(
                tool_name=tool_call.name,
                success=True,
                result=result,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"[Runtime] 工具执行失败: {tool_call.name}, 错误: {str(e)}")
            
            return ToolResult(
                tool_name=tool_call.name,
                success=False,
                result=None,
                error=str(e),
                execution_time_ms=execution_time
            )
    
    async def execute_tools(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
        """
        执行多个工具调用
        
        Args:
            tool_calls: 工具调用列表
            
        Returns:
            执行结果列表
        """
        results = []
        for tc in tool_calls:
            result = await self.execute_tool(tc)
            results.append(result)
        return results
    
    def get_execution_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self._execution_history[-limit:]


# 全局运行时实例
_runtime: Optional[ToolRuntime] = None


def get_runtime() -> ToolRuntime:
    """获取全局运行时实例"""
    global _runtime
    if _runtime is None:
        _runtime = ToolRuntime()
    return _runtime
