# mini_code

`mini_code` 是一个模块化 Python 代理项目，提供可维护的包结构、CLI、运行时调度、任务系统和团队协作能力。

## 安装

```bash
python3 -m pip install -e .
```

运行前需要设置：

```bash
export MODEL_ID=your-model-id
export ANTHROPIC_API_KEY=your-api-key
```

可选：

```bash
export ANTHROPIC_BASE_URL=https://your-proxy.example.com
```

## 最小使用

进入交互会话：

```bash
mini-code chat
```

查看任务板：

```bash
mini-code tasks list
```

查看团队状态：

```bash
mini-code team list
```

## 目录结构

```text
src/mini_code/
  config.py
  llm.py
  prompting.py
  runtime.py
  cli.py
  tools/
  features/
docs/
tests/
```

## 设计原则

- 使用清晰的模块边界组织配置、工具、运行时和业务能力
- 所有状态继续落在工作区本地目录，例如 `.tasks`、`.team`、`.transcripts`
- 优先保证 CLI、运行时和测试之间的可组合性
- Anthropic 是当前唯一支持的 LLM provider

更多说明见：

- [`docs/reference-analysis.md`](/home/john/Code/mini-code/docs/reference-analysis.md)
- [`docs/architecture.md`](/home/john/Code/mini-code/docs/architecture.md)
- [`docs/user-guide.md`](/home/john/Code/mini-code/docs/user-guide.md)
