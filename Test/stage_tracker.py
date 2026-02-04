"""
Stage Tracker - 自动化阶段验证

负责:
- 验证物理目录创建
- 验证 UI 网络地址可访问性
- 验证 LLM 连通性
- 记录验证结果
"""

import os
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import aiohttp


@dataclass
class CheckResult:
    """检查结果"""
    name: str
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }
    
    def to_markdown(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"- **{self.name}**: {status}\n  - {self.message}"


@dataclass
class StageResult:
    """阶段验证结果"""
    stage: str
    checks: List[CheckResult]
    start_time: datetime
    end_time: Optional[datetime] = None
    
    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)
    
    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "all_passed": self.all_passed,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "checks": [c.to_dict() for c in self.checks],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None
        }
    
    def to_markdown(self) -> str:
        status = "✅ 通过" if self.all_passed else "❌ 未完全通过"
        lines = [
            f"## {self.stage}",
            f"",
            f"**状态**: {status}",
            f"**通过**: {self.passed_count}/{len(self.checks)}",
            f"**时间**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            "### 检查项:",
            ""
        ]
        
        for check in self.checks:
            lines.append(check.to_markdown())
        
        return "\n".join(lines)


class StageTracker:
    """
    阶段跟踪器
    
    执行和跟踪各阶段的验证
    """
    
    # 预期的目录结构
    EXPECTED_DIRECTORIES = [
        "UI",
        "UI/templates",
        "UI/static",
        "UI/static/css",
        "UI/static/js",
        "LLM",
        "Gateway",
        "Tools",
        "Tools/builtins",
        "Memory",
        "Config",
        "Logging",
        "Security",
        "Bridge",
        "Test"
    ]
    
    # 预期的核心文件
    EXPECTED_FILES = [
        "UI/__init__.py",
        "UI/web_server.py",
        "UI/templates/index.html",
        "UI/static/css/style.css",
        "UI/static/js/chat.js",
        "LLM/__init__.py",
        "LLM/client.py",
        "LLM/prompt_tmplt.py",
        "LLM/adapter.py",
        "Gateway/__init__.py",
        "Gateway/api.py",
        "Gateway/session.py",
        "Gateway/channel.py",
        "Gateway/planner.py",
        "Gateway/runtime.py",
        "Gateway/memory_bridge.py",
        "Gateway/policy.py",
        "Gateway/observability.py",
        "Tools/__init__.py",
        "Tools/adapters.py",
        "Tools/registry.py",
        "Tools/capability.py",
        "Tools/simulator.py",
        "Tools/metadata.py",
        "Memory/__init__.py",
        "Memory/short_term.py",
        "Memory/long_term.py",
        "Memory/vector_store.py",
        "Memory/query_module.py",
        "Memory/policy.py",
        "Memory/serialization.py",
        "Memory/access_control.py",
        "Config/__init__.py",
        "Config/manager.py",
        "Logging/__init__.py",
        "Security/__init__.py",
        "Bridge/__init__.py",
        "Bridge/dispatcher.py",
        "Test/__init__.py",
        "Test/stage_tracker.py",
        "main.py",
        "requirements.txt"
    ]
    
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.results: List[StageResult] = []
    
    def check_directories(self) -> List[CheckResult]:
        """检查目录结构"""
        results = []
        
        for dir_path in self.EXPECTED_DIRECTORIES:
            full_path = self.base_path / dir_path
            exists = full_path.exists() and full_path.is_dir()
            
            results.append(CheckResult(
                name=f"目录: {dir_path}",
                passed=exists,
                message="目录存在" if exists else "目录不存在",
                details={"path": str(full_path)}
            ))
        
        return results
    
    def check_files(self) -> List[CheckResult]:
        """检查核心文件"""
        results = []
        
        for file_path in self.EXPECTED_FILES:
            full_path = self.base_path / file_path
            exists = full_path.exists() and full_path.is_file()
            
            results.append(CheckResult(
                name=f"文件: {file_path}",
                passed=exists,
                message="文件存在" if exists else "文件不存在",
                details={"path": str(full_path)}
            ))
        
        return results
    
    async def check_ui_accessibility(
        self,
        host: str = "localhost",
        port: int = 8000,
        timeout: int = 5
    ) -> CheckResult:
        """
        检查 UI 网络地址可访问性
        
        Args:
            host: 主机地址
            port: 端口
            timeout: 超时时间(秒)
            
        Returns:
            检查结果
        """
        url = f"http://{host}:{port}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        return CheckResult(
                            name="UI 网络访问",
                            passed=True,
                            message=f"UI 可通过 {url} 访问",
                            details={
                                "url": url,
                                "status_code": response.status
                            }
                        )
                    else:
                        return CheckResult(
                            name="UI 网络访问",
                            passed=False,
                            message=f"UI 返回非 200 状态码: {response.status}",
                            details={
                                "url": url,
                                "status_code": response.status
                            }
                        )
        except asyncio.TimeoutError:
            return CheckResult(
                name="UI 网络访问",
                passed=False,
                message=f"连接 {url} 超时",
                details={"url": url, "error": "timeout"}
            )
        except Exception as e:
            return CheckResult(
                name="UI 网络访问",
                passed=False,
                message=f"无法连接到 {url}: {str(e)}",
                details={"url": url, "error": str(e)}
            )
    
    async def check_llm_connectivity(
        self,
        host: str = "http://localhost:11434",
        timeout: int = 10
    ) -> CheckResult:
        """
        检查 LLM (Ollama) 连通性
        
        Args:
            host: Ollama 服务地址
            timeout: 超时时间(秒)
            
        Returns:
            检查结果
        """
        try:
            from LLM.client import OllamaClient
            
            client = OllamaClient(host=host, timeout=timeout)
            result = await client.test_connection()
            await client.close()
            
            if result.get("success"):
                models = result.get("available_models", [])
                target_available = result.get("target_model_available", False)
                
                return CheckResult(
                    name="LLM 连通性",
                    passed=True,
                    message=f"Ollama 服务可用,发现 {len(models)} 个模型",
                    details={
                        "host": host,
                        "available_models": models,
                        "target_model": result.get("target_model"),
                        "target_model_available": target_available
                    }
                )
            else:
                return CheckResult(
                    name="LLM 连通性",
                    passed=False,
                    message=f"Ollama 连接失败: {result.get('error', 'Unknown error')}",
                    details={"host": host, "error": result.get("error")}
                )
        except ImportError:
            return CheckResult(
                name="LLM 连通性",
                passed=False,
                message="无法导入 LLM 模块",
                details={"error": "ImportError"}
            )
        except Exception as e:
            return CheckResult(
                name="LLM 连通性",
                passed=False,
                message=f"LLM 连接测试失败: {str(e)}",
                details={"host": host, "error": str(e)}
            )
    
    async def run_stage1_verification(
        self,
        check_ui: bool = True,
        check_llm: bool = True,
        ui_host: str = "localhost",
        ui_port: int = 8000,
        llm_host: str = "http://localhost:11434"
    ) -> StageResult:
        """
        运行第一阶段验证
        
        Args:
            check_ui: 是否检查 UI 可访问性
            check_llm: 是否检查 LLM 连通性
            ui_host: UI 主机地址
            ui_port: UI 端口
            llm_host: LLM 服务地址
            
        Returns:
            阶段验证结果
        """
        start_time = datetime.now()
        checks = []
        
        # 1. 检查目录结构
        dir_checks = self.check_directories()
        
        # 汇总目录检查
        dir_passed = sum(1 for c in dir_checks if c.passed)
        checks.append(CheckResult(
            name="目录结构检查",
            passed=dir_passed == len(dir_checks),
            message=f"通过 {dir_passed}/{len(dir_checks)} 个目录检查",
            details={"checks": [c.to_dict() for c in dir_checks]}
        ))
        
        # 2. 检查核心文件
        file_checks = self.check_files()
        
        # 汇总文件检查
        file_passed = sum(1 for c in file_checks if c.passed)
        checks.append(CheckResult(
            name="核心文件检查",
            passed=file_passed == len(file_checks),
            message=f"通过 {file_passed}/{len(file_checks)} 个文件检查",
            details={"checks": [c.to_dict() for c in file_checks]}
        ))
        
        # 3. 检查 UI 可访问性
        if check_ui:
            ui_result = await self.check_ui_accessibility(ui_host, ui_port)
            checks.append(ui_result)
        
        # 4. 检查 LLM 连通性
        if check_llm:
            llm_result = await self.check_llm_connectivity(llm_host)
            checks.append(llm_result)
        
        result = StageResult(
            stage="第一阶段: 项目骨架初始化",
            checks=checks,
            start_time=start_time,
            end_time=datetime.now()
        )
        
        self.results.append(result)
        
        return result
    
    def write_verification_log(
        self,
        result: StageResult,
        log_path: Optional[str] = None
    ) -> str:
        """
        写入验证日志
        
        Args:
            result: 阶段验证结果
            log_path: 日志文件路径
            
        Returns:
            日志内容
        """
        if log_path is None:
            log_path = self.base_path / "Test" / "verification_logs.md"
        else:
            log_path = Path(log_path)
        
        # 生成日志内容
        content = f"""# OpenClaw 验证日志

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

{result.to_markdown()}

---

## 详细信息

### 检查摘要

| 检查项 | 状态 | 说明 |
|--------|------|------|
"""
        
        for check in result.checks:
            status = "✅" if check.passed else "❌"
            content += f"| {check.name} | {status} | {check.message} |\n"
        
        content += f"""
### 环境信息

- **Python 版本**: 请运行 `python --version` 查看
- **项目路径**: `{self.base_path.absolute()}`
- **验证时间**: {result.start_time.strftime('%Y-%m-%d %H:%M:%S')}

### 下一步

"""
        
        if result.all_passed:
            content += """所有检查通过！可以继续进行下一阶段的开发。

1. 运行 `python main.py` 启动应用
2. 访问 UI 地址进行测试
3. 开始实现具体功能
"""
        else:
            content += """部分检查未通过，请检查以下问题：

"""
            for check in result.checks:
                if not check.passed:
                    content += f"- **{check.name}**: {check.message}\n"
        
        # 写入文件
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return content


async def run_stage1_verification(
    base_path: str = ".",
    check_ui: bool = False,
    check_llm: bool = True
) -> StageResult:
    """
    运行第一阶段验证的便捷函数
    
    Args:
        base_path: 项目基础路径
        check_ui: 是否检查 UI (默认关闭,因为服务可能未启动)
        check_llm: 是否检查 LLM
        
    Returns:
        验证结果
    """
    tracker = StageTracker(base_path)
    result = await tracker.run_stage1_verification(
        check_ui=check_ui,
        check_llm=check_llm
    )
    tracker.write_verification_log(result)
    return result


if __name__ == "__main__":
    # 直接运行时执行验证
    import sys
    
    async def main():
        # 获取项目根目录
        script_path = Path(__file__).parent.parent
        
        print("=" * 60)
        print("OpenClaw 第一阶段验证")
        print("=" * 60)
        print()
        
        result = await run_stage1_verification(
            base_path=str(script_path),
            check_ui=False,
            check_llm=True
        )
        
        print(result.to_markdown())
        print()
        print("=" * 60)
        print(f"验证日志已写入: Test/verification_logs.md")
        print("=" * 60)
        
        sys.exit(0 if result.all_passed else 1)
    
    asyncio.run(main())
