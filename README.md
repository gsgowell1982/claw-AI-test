# claw-AI-test
openclaw-local-test
# 🚀 OpenClaw: 本地强化型 AI Agent 助手 (v2.3)

OpenClaw 是一个基于本地 LLM (当前：Qwen2.5:7b) 构建的智能体。它不仅具备流式对话能力，更拥有**本地文件感知**、**自动化执行**和**外部 API 联动**的核心能力。

---

## 📂 项目架构与目录结构

```text
OpenClaw/
├── Gateway/            # 核心网关层：处理 API、WebSocket 及任务规划 (Planner)
├── Bridge/             # 桥接层：指令分发器，控制 Agent 思考循环 (Dispatcher)
├── LLM/                # 模型适配层：对接 Ollama OpenAI 兼容接口
├── Tools/              # 工具库：内置文件读写、GitHub API、系统指令等
├── UI/                 # 前端界面：基于 HTML/JS 的流式聊天交互窗口
├── Memory/             # 存储层：(Phase 4) 向量数据库与 SQLite 持久化存储
├── Config/             # 配置管理：加载 .env (GitHub Token) 与系统设置
└── main.py             # 项目入口：启动 FastAPI 高性能服务

```
已实现阶段成果 (Phase 1-3)
第一 & 二阶段：通信与流式响应
模型对接：完美适配本地 Ollama (当前模型：Qwen2.5:7b)。
流式交互：实现 WebSocket 双向流式通信，支持打字机效果。
生命周期：具备优雅的服务启动/关闭与资源回收机制。
---
第三阶段：Agent 执行力与工具调用 (当前状态)
文件操作能力：

list_files：实时查看本地项目目录结构。

read_file / write_file：直接读取源码并根据需求自动重写或新建 Python 脚本。

GitHub 深度联动：

支持 github_set_token 动态注入。

具备根据用户意图在远程 GitHub 账号下创建新仓库（Repository）的能力。

自我修正逻辑：模型在工具调用失败（如参数错误）时，能够根据错误反馈自动尝试第二轮调用。
---
即将进行的第四阶段：知识库增强与复杂任务编排
本阶段目标是让 OpenClaw 从“工具使用者”升级为“拥有长期记忆的项目专家”。
---
快速上手
准备环境：

运行本地 Ollama，确保有 qwen2.5:7b 模型。

安装依赖：pip install -r requirements.txt
---
启动服务：
```text
python main_v2_3.py
```
