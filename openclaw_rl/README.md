# OpenClaw Tinker RL

这个子目录用于在 **OpenClaw 所在机器** 上直接启动 OpenClaw-RL 的 Tinker 版本。这样 OpenClaw 与本地代理走 `127.0.0.1`，不需要跨网络暴露端口，通常是最稳的接法。

## 目录内容

- `run.sh`：自动拉取上游 `Gen-Verse/OpenClaw-RL`、创建 `.venv`、安装依赖并启动 `openclaw-tinker/run.py`
- `env.example`：本地配置模板
- `.gitignore`：忽略 `.env`、`.venv`、运行记录以及自动 clone 下来的上游仓库

## 首次使用

1. 把这个仓库 clone 到 OpenClaw 所在机器。
2. 进入本目录：

   ```bash
   cd openclaw_rl
   ```

3. 复制配置模板：

   ```bash
   cp env.example .env
   ```

4. 编辑 `.env`，至少填好：

   ```bash
   TINKER_API_KEY=你的_tinker_key
   ```

5. 启动：

   ```bash
   bash run.sh
   ```

默认配置会：

- 使用 `combine`
- 使用 `Qwen/Qwen3.5-4B`
- batch size 为 `8`
- `prm-m=1`
- 代理监听 `127.0.0.1:30000`

## OpenClaw 接入方式

因为这里建议直接在 OpenClaw 同机部署，所以 OpenClaw 里把 provider 指向：

- Base URL: `http://127.0.0.1:30000/v1`
- API key: `.env` 里的 `SGLANG_API_KEY`
- Model: `sglang/qwen3.5-4b-tinker`

如果你的 OpenClaw 只接受裸模型名，也可以填：

- `qwen3.5-4b-tinker`

## 真实轨迹训练必需项

要让会话被正确归类为 RL 训练轨迹，需要在 OpenClaw 中安装上游项目自带的扩展：

```text
OpenClaw-RL/extensions/rl-training-headers
```

`run.sh` 第一次运行后会自动把上游仓库 clone 到当前目录下的：

```text
openclaw_rl/OpenClaw-RL
```

安装扩展时可以直接用这个路径。它会自动加上：

- `X-Session-Id`
- `X-Turn-Type`

这两个头是 personal trajectory 采集的关键。

## 常用修改

切到 8B：

```bash
OPENCLAW_MODEL_NAME=Qwen/Qwen3-8B \
OPENCLAW_SERVED_MODEL_NAME=qwen3-8b-tinker \
bash run.sh
```

把额外参数透传给上游入口：

```bash
bash run.sh --teacher-model-name Qwen/Qwen3-8B --save-interval 10
```

## 健康检查

本机测试：

```bash
curl http://127.0.0.1:30000/healthz
```

最小聊天测试：

```bash
curl http://127.0.0.1:30000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3.5-4b-tinker",
    "messages": [{"role": "user", "content": "你好，做个自我介绍"}],
    "stream": false
  }'
```

## 后续改算法

如果你后面要改 Tinker 侧的训练逻辑，通常改这些文件：

- `OpenClaw-RL/openclaw-tinker/trainer.py`
- `OpenClaw-RL/openclaw-tinker/scorers.py`
- `OpenClaw-RL/openclaw-tinker/data_formatter.py`
- `OpenClaw-RL/openclaw-tinker/api_server.py`
- `OpenClaw-RL/openclaw-tinker/rollout.py`

为了避免覆盖你本地改动，开发期间建议保持：

```bash
OPENCLAW_RL_AUTO_UPDATE=0
```
