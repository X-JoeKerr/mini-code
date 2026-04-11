# 项目能力概览

## 核心模块

当前项目包含以下核心能力模块：

- 大输出持久化与预览标记
- 文件工具：`bash`、`read_file`、`write_file`、`edit_file`
- `TodoManager`
- `run_subagent`
- `SkillLoader`
- `microcompact` 和 `auto_compact`
- `TaskManager`
- `BackgroundManager`
- `MessageBus`
- `TeammateManager`
- `shutdown_requests` 与 `plan_requests`
- `TOOL_HANDLERS`、`TOOLS`
- `agent_loop`
- REPL 入口

## 关键状态目录

项目在工作区下维护这些目录：

- `.team`
- `.team/inbox`
- `.tasks`
- `skills`
- `.transcripts`
- `.task_outputs/tool-results`

这些状态目录统一由 `WorkspacePaths` 管理。

## 主执行流程

项目的主要运行路径如下：

1. 读取环境变量并初始化 Anthropic client。
2. 创建配置对象、provider 以及各类 manager。
3. REPL 持续读取用户输入。
4. 用户输入进入 `AgentRuntime.agent_loop()`。
5. 运行时先做 `microcompact` 和 token 阈值判断，必要时触发 `auto_compact`。
6. 然后吸收后台任务通知和 lead inbox 消息。
7. 调用模型，得到文本或工具请求。
8. 若模型请求工具，则查 runtime 的 handler 映射执行并把结果回注入历史。
9. 若触发手动压缩，则再次运行 `auto_compact`。

## 工具清单

当前项目定义了以下主工具：

- `bash`
- `read_file`
- `write_file`
- `edit_file`
- `TodoWrite`
- `task`
- `load_skill`
- `compress`
- `background_run`
- `check_background`
- `task_create`
- `task_get`
- `task_update`
- `task_list`
- `spawn_teammate`
- `list_teammates`
- `send_message`
- `read_inbox`
- `broadcast`
- `shutdown_request`
- `plan_approval`
- `idle`
- `claim_task`

## 队友协作机制

`TeammateManager` 会：

- 在 `.team/config.json` 里记录成员状态
- 为每个队友起一个工作线程
- 给队友提供有限工具集
- 在工作阶段响应收件箱消息
- 在 idle 阶段轮询新消息和可认领任务
- 超时后自动进入 shutdown

这套机制通过显式依赖注入完成组装，方便测试和替换。

## 模块拆分

项目按以下边界组织：

- `config`
- `llm`
- `tools`
- `features`
- `runtime`
- `cli`

这种结构让功能扩展、测试编写和 CLI 维护更直接。
