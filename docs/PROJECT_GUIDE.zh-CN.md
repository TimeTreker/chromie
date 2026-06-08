# Chromie 中文项目指南

Chromie 是一个本地运行、GPU 加速的实时语音助手项目。它把语音识别、意图路由、多智能体处理、大语言模型和语音合成拆分成独立服务，并由宿主机上的编排器统一管理麦克风、播放、打断和会话状态。

本文适合第一次接触项目的开发者，目标是帮助你完成四件事：

1. 理解 Chromie 的整体架构。
2. 根据本机硬件生成配置。
3. 启动并验证完整语音链路。
4. 在出现问题时快速定位负责的组件。

> 本文说明的是当前仓库中的实现。各组件的接口细节请继续参考根目录及子目录中的 README。

## 一、工作原理

一次正常的语音交互按以下顺序执行：

```text
麦克风
  ↓
宿主机 Orchestrator：采集音频、VAD、打断和会话管理
  ↓
chromie-asr：语音转文字
  ↓
chromie-router：快速判断意图和需要调用的 Agent
  ↓
chromie-agent：生成回答、动作计划和记忆更新
  ↓
chromie-llm：通过 Ollama 提供本地大模型推理
  ↓
chromie-tts：把回答合成为音频流
  ↓
宿主机 Orchestrator：播放语音并执行可选硬件动作
```

最重要的边界是：

- ASR、Router、Agent、LLM 和 TTS 在 Docker 中运行。
- Orchestrator 在宿主机运行，因为它需要直接访问麦克风、扬声器和本地音频设备。
- Router 负责快速决策，默认使用规则路由；Agent 才是主要的对话和规划组件。
- Router 和 Agent 不直接播放声音，也不直接控制硬件。

这种拆分让每个组件职责清楚，也便于分别查看日志、替换模型和定位性能瓶颈。

## 二、服务与端口

| 组件 | 运行位置 | 默认端口 | 主要职责 |
|---|---|---:|---|
| `chromie-asr` | Docker | `9001` | Faster-Whisper WebSocket 语音识别 |
| `chromie-tts` | Docker | `5000` | OuteTTS / llama.cpp WebSocket 语音合成 |
| `chromie-llm` | Docker | `11434` | Ollama 模型服务 |
| `chromie-router` | Docker | `8091` | 意图识别与任务路由 |
| `chromie-agent` | Docker | `8092` | 对话、动作、安全、工具和记忆处理 |
| Orchestrator | 宿主机 | 无 | 音频输入输出、VAD、打断、会话与服务编排 |
| Hardware daemon | 宿主机，可选 | `8095` | 执行机器人硬件动作 |

## 三、运行前准备

当前桌面端配置主要面向 Linux、NVIDIA GPU 和 NVIDIA Container Toolkit。至少需要：

- Docker 和 Docker Compose。
- 可被容器访问的 NVIDIA GPU 与驱动。
- Conda；默认环境名为 `Chromie`。
- 可用的麦克风和扬声器。
- 足够的磁盘空间存放 Hugging Face、Ollama 和 TTS 模型。

先检查基础环境：

```bash
nvidia-smi
docker compose version
conda --version
```

仓库已提供 RTX 4090、RTX 5090 和若干 Jetson 硬件配置。Jetson 配置目前定义了模型和运行参数，但完整部署仍可能需要 ARM64/Jetson 专用 Dockerfile 或 Compose override，不能仅凭选中 profile 就认为已完成兼容。

## 四、配置方式

Chromie 不建议直接维护一份庞大的 `.env`。运行时配置按以下顺序合并：

```text
.env.common
  + env/profiles/<硬件配置>.env
  + .env.local
  ↓
.env.runtime
```

各文件职责如下：

| 文件 | 用途 | 是否提交 |
|---|---|---|
| `.env.common` | 全平台公共默认值 | 是 |
| `env/profiles/*.env` | 硬件相关模型和性能参数 | 是 |
| `.env.local` | 当前机器的个性化覆盖 | 否 |
| `.env.runtime` | 脚本自动生成的最终配置 | 否 |

创建本机覆盖文件：

```bash
cp .env.local.example .env.local
```

查看自动识别的硬件和关键参数：

```bash
./scripts/show_profile.sh
```

如需手动指定硬件或模型，可在 `.env.local` 中覆盖：

```env
CHROMIE_HARDWARE_PROFILE=rtx4090
AGENT_MODEL=gemma4:e2b
ROUTER_USE_LLM=0
```

`.env.local` 的优先级最高。不要直接修改自动生成的 `.env.runtime`，否则下次运行脚本时改动会被覆盖。

### 关键参数

| 参数 | 含义 |
|---|---|
| `AGENT_MODEL` | Agent 使用的 Ollama 对话模型 |
| `ROUTER_USE_LLM` | 是否使用 LLM 辅助路由；默认关闭以降低延迟 |
| `AGENT_MAX_SPEAK_CHARS` | Agent 最长口语回答字符数 |
| `TTS_MAX_TEXT_CHARS` | 单次送入 TTS 的文本字符上限 |
| `TTS_MAX_LENGTH` | TTS 模型生成预算，不是文本长度 |
| `ORCH_AGENT_TIMEOUT_MS` | Orchestrator 等待 Agent 的超时时间 |
| `HTTP_PROXY` / `HTTPS_PROXY` | 容器下载模型时使用的可选代理 |

不要用很小的 `TTS_MAX_LENGTH` 来缩短回答。需要减少播报内容时，应调整 `AGENT_MAX_SPEAK_CHARS` 或 `TTS_MAX_TEXT_CHARS`。

## 五、启动项目

### 1. 启动 Docker 服务

首次启动或代码、依赖发生变化时构建镜像：

```bash
BUILD=1 ./scripts/start_services.sh
```

已有镜像时直接启动：

```bash
./scripts/start_services.sh
```

需要完全重新构建时：

```bash
REBUILD_NO_CACHE=1 ./scripts/start_services.sh
```

启动脚本会自动：

- 检测硬件并生成 `.env.runtime`。
- 创建 `hf_cache/`、`ollama_data/` 和 `recordings/`。
- 启动 ASR、TTS、Ollama、Router 和 Agent。
- 输出容器状态及常用后续命令。

### 2. 确认并准备 Ollama 模型

查看已经安装的模型：

```bash
docker compose --env-file .env.runtime exec chromie-llm ollama list
```

如果 profile 指定的模型尚未安装，请拉取对应模型，例如：

```bash
set -a
source .env.runtime
set +a
docker compose --env-file .env.runtime exec chromie-llm ollama pull "$AGENT_MODEL"
```

大型模型第一次加载可能很慢。开始语音交互前先预热：

```bash
./scripts/warm_ollama.sh
```

### 3. 配置宿主机音频

如果 Conda 环境尚未创建，先准备环境并安装宿主机依赖：

```bash
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh
```

如需使用其他环境名，在根目录 `.env.local` 中设置 `CHROMIE_CONDA_ENV`。

Orchestrator 的机器相关设置放在 `orchestrator/.env.local`：

```bash
cp orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

根据输出填写真实的输入和输出设备编号。尽量避免选择 `default`、`sysdefault`、`pipewire`、`monitor`、`Default Sink` 或 `Default Source` 之类的通用设备。

使用 `ORCH_INPUT_DEVICE` 和 `ORCH_OUTPUT_DEVICE` 指定设备。`RECORDINGS_DIR` 如果使用相对路径，将以仓库根目录为基准解析。

### 4. 启动 Orchestrator

```bash
./scripts/start_orchestrator.sh
```

该脚本会生成运行时配置、激活 Conda 环境、检查依赖、预热模型并启动：

```bash
python -m orchestrator.orchestrator
```

同一时间只应运行一个 Orchestrator。重复进程会同时监听麦克风，并可能造成同一句回答被合成和播放多次。启动脚本使用锁文件阻止常见的重复启动。

## 六、验证运行状态

先查看所有容器：

```bash
docker compose --env-file .env.runtime ps
```

Router、Agent 和 Ollama 可以通过 HTTP 验证：

```bash
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8092/health
curl -fsS http://127.0.0.1:11434/api/tags
```

验证 TTS 是否真正使用 GPU：

```bash
./scripts/verify_tts_gpu.sh
```

完整链路验证时，可以说一句简短的话，并观察是否依次出现：

1. Orchestrator 检测到语音结束。
2. ASR 返回文本。
3. Router 返回路由结果。
4. Agent 返回回答或动作计划。
5. TTS 生成音频。
6. Orchestrator 播放音频。

## 七、日志与常见问题

### 查看组件日志

```bash
docker compose --env-file .env.runtime logs -f chromie-asr
docker compose --env-file .env.runtime logs -f chromie-router
docker compose --env-file .env.runtime logs -f chromie-agent
docker compose --env-file .env.runtime logs -f chromie-llm
docker compose --env-file .env.runtime logs -f chromie-tts
```

| 问题 | 优先检查 | 常见原因 |
|---|---|---|
| Agent 总是返回固定短句 | `chromie-agent`、`chromie-llm` 日志 | 模型未安装、Agent 未启用 LLM 或请求超时 |
| 首次对话超时 | Ollama 日志及模型预热 | 大模型尚未加载 |
| 同一句话播放两次 | Orchestrator 进程和 TTS request ID | 同时运行了多个 Orchestrator |
| TTS 很慢或只用 CPU | `verify_tts_gpu.sh` 和 TTS 日志 | 镜像未按正确 CUDA 架构构建 |
| 音频速度异常 | 输出设备和采样率 | 选中了错误或通用音频设备 |
| TTS 不生成音频 | `TTS_MAX_LENGTH` | 误把生成预算设置成了很小的文本长度 |
| Jetson 无法构建或启动 | 架构、基础镜像、Compose override | 当前 profile 不等于完整的 Jetson 容器适配 |

检查是否存在旧的 Orchestrator 进程：

```bash
pgrep -af "orchestrator"
```

如果 Agent 报告模型不可用，确认实际配置和已安装模型：

```bash
docker compose --env-file .env.runtime exec chromie-agent env \
  | grep -E "AGENT_USE_LLM|AGENT_OLLAMA_URL|AGENT_MODEL|AGENT_TIMEOUT_MS"
docker compose --env-file .env.runtime exec chromie-llm ollama list
```

## 八、进一步阅读

- [根目录 README](../README.md)：完整英文部署和调试说明。
- [硬件配置说明](../HARDWARE_PROFILES.md)：profile 合并规则和硬件参数。
- [运维手册](../CHROMIE_RUNBOOK.md)：日常启动和诊断命令。
- [Orchestrator](../orchestrator/README.md)：宿主机实时音频编排。
- [Router](../router/README.md)：路由 API 和配置。
- [Agent](../agent/README.md)：多智能体职责和 API。
- [Hardware](../hardware/README.md)：可选硬件动作服务。
- [会话状态](conversation_state.md)：多轮上下文与会话边界。
- [能力注册表](agent_capability_registry.md)：Agent 工具能力和安全可见性。
- [任务图](agent_task_graph.md)：多步骤任务的校验与执行。

Chromie 的核心设计原则可以概括为：让 Orchestrator 管实时音频，让 Router 快速做决定，让 Agent 负责思考和规划，让每个模型服务保持独立、可观察和可替换。

## 九、运行测试

首次运行时安装轻量测试依赖：

```bash
INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh
```

之后直接运行：

```bash
./scripts/run_tests.sh
```

这套测试不需要 Docker、GPU、模型、音频设备或真实机器人硬件，覆盖 Router、跨服务数据契约、会话状态、Agent 安全策略、确认拦截和 mock hardware 链路。
