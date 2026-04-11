# 架构说明

## 总体结构

项目采用 `src` 布局，并把系统拆成 4 层：

- `cli`
- `runtime`
- `features` 与 `tools`
- `llm` 与 `config`

依赖方向固定为：

- `cli -> runtime`
- `runtime -> features/tools/llm/prompting`
- `features/team -> llm/tools/tasks`
- `tools` 不依赖 `runtime`

## 模块职责

### `config.py`

- 加载环境变量
- 默认从工作区 `.env` 或 `MINI_CODE_ENV_FILE` 加载环境文件
- 校验 `MODEL_ID`
- 统一工作区路径
- 暴露运行阈值配置

### `llm.py`

- 封装 Anthropic client 初始化
- 暴露统一 `create_message(...)`
- 提供内容块标准化工具

### `tools/`

- `files.py`：工作区安全路径、文件读写改、shell 执行、大输出落盘
- `subagent.py`：隔离的子代理循环

### `features/`

- `todo.py`：短期 Todo 列表
- `skills.py`：`SKILL.md` 发现和加载
- `tasks.py`：持久任务板
- `background.py`：后台命令执行与通知
- `team.py`：消息总线、队友线程、关停和审批协议

### `runtime.py`

- 工具 schema 定义
- handler 调度
- 自动压缩
- 主代理循环
- 背景通知与收件箱注入

### `cli.py`

- 用 `argparse` 暴露子命令
- 提供交互式 `chat`
- 通过 `build_app()` 统一创建依赖

## 工作区状态目录

运行过程中会用到以下目录：

- `.team`
- `.team/inbox`
- `.tasks`
- `skills`
- `.transcripts`
- `.task_outputs/tool-results`

这些目录都被视为“工作区状态”，不会打包到源码目录中。

## 运行生命周期

1. CLI 调用 `build_app()`。
2. `build_app()` 创建 `AppConfig`、provider、各类 manager 和 `AgentRuntime`。
3. `chat` 模式把输入追加到 `history`。
4. `AgentRuntime.agent_loop()` 调模型并处理工具调用。
5. 工具结果写回历史，必要时进行压缩。
6. `tasks/team/bg` 子命令则直接调用对应 manager。

## 设计结果

当前架构的重点是：

- 保留工作区状态模型
- 保留核心工具和团队能力
- 保留 `chat` 和任务板语义
- 通过对象组装替代隐式全局依赖
- 让 CLI、runtime 和 feature 层可以独立测试
