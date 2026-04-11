# 使用说明

## 环境变量

至少需要：

```bash
export MODEL_ID=your-model-id
export ANTHROPIC_API_KEY=your-api-key
```

可选变量：

```bash
export ANTHROPIC_BASE_URL=https://your-proxy.example.com
```

## 交互会话

启动：

```bash
mini-code chat
```

可用内置命令：

- `/compact`
- `/tasks`
- `/team`
- `/inbox`
- `exit`
- `q`

空行也会退出会话。

## 任务命令

列出任务：

```bash
mini-code tasks list
```

创建任务：

```bash
mini-code tasks create "实现文档" --description "补充 docs"
```

更新任务：

```bash
mini-code tasks update 1 --status completed
```

## 团队命令

查看成员：

```bash
mini-code team list
```

生成队友：

```bash
mini-code team spawn writer documentation "Write the docs"
```

发送消息：

```bash
mini-code team send writer "Please summarize your findings."
```

读取 lead inbox：

```bash
mini-code team inbox
```

## 后台任务命令

查看后台任务概览：

```bash
mini-code bg list
```

查询单个后台任务：

```bash
mini-code bg get abc12345
```

## 常见问题

### `MODEL_ID environment variable is required`

说明尚未设置 `MODEL_ID`。

### `anthropic package is not installed`

说明依赖未安装，请先执行：

```bash
python3 -m pip install -e .
```

### 队友命令看起来没有长期驻留

当前队友仍是进程内线程模型，最适合在 `chat` 会话或库内长生命周期进程中使用。独立 CLI 子命令可触发它，但不会提供额外的守护进程能力。
