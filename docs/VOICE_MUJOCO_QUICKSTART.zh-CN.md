# Chromie 语音到 MuJoCo 一键运行

本指南用于日常交互运行，不是验收流程。目标是启动完整链路：

```text
麦克风 -> Chromie ASR/Router/Agent -> Soridormi MCP -> MuJoCo
扬声器 <- Chromie TTS
```

## 目录布局

默认将两个仓库放在同一父目录：

```text
projects/
├── chromie/
└── soridormi/
```

Soridormi 在其他位置时，通过参数指定：

```bash
./scripts/start_voice_mujoco.sh --soridormi-repo /path/to/soridormi
```

## Soridormi 首次准备

在 Soridormi 仓库中完成一次初始化：

```bash
cd ../soridormi
./scripts/add_submodules.sh
./scripts/setup_env.sh
./scripts/build_sim.sh
```

## Chromie 音频设置

第一次使用时：

```bash
cd ../chromie
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh
cp -n orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

可以在 `orchestrator/.env.local` 中填写：

```env
ORCH_INPUT_DEVICE=麦克风名称或编号
ORCH_OUTPUT_DEVICE=扬声器名称或编号
```

留空时使用操作系统默认设备。

## 第一次完整启动

从 Chromie 仓库根目录运行：

```bash
./scripts/start_voice_mujoco.sh --build
```

启动器会依次：

1. 打开带跟随摄像机的 MuJoCo viewer；
2. 启动 Soridormi runtime-backed MCP 服务；
3. 启动 Chromie ASR、TTS、Ollama、Router 和 Agent；
4. 验证 Soridormi capability contract；
5. 启动主机 Orchestrator，并打开麦克风和扬声器。

看到下面的信息后即可说话：

```text
Chromie voice-to-MuJoCo is ready
```

示例：

```text
Please nod twice.
Look at me for three seconds.
What is the robot status?
Stop.
```

默认允许 Soridormi 清单中明确声明的模拟器免确认技能立即执行。希望每次动作都经过语音确认时：

```bash
./scripts/start_voice_mujoco.sh --require-confirmation
```

## 日常启动

镜像已经构建后：

```bash
./scripts/start_voice_mujoco.sh
```

无图形桌面时：

```bash
./scripts/start_voice_mujoco.sh --no-viewer
```

## 查看状态

在另一个终端中：

```bash
./scripts/status_voice_mujoco.sh
```

全部组件正常时，每一项都显示 `[READY]`。

## 停止

在启动器终端按 `Ctrl+C`。启动器默认停止由它启动的完整栈。

也可以从另一个终端强制停止：

```bash
./scripts/stop_voice_mujoco.sh
```

希望关闭 Orchestrator 后仍保留容器和模拟器时：

```bash
./scripts/start_voice_mujoco.sh --keep-running
```

## 日志

统一启动器日志目录：

```text
.chromie/voice-mujoco/logs/
```

Chromie 容器日志：

```bash
docker compose --env-file .env.runtime logs -f chromie-asr
docker compose --env-file .env.runtime logs -f chromie-agent
docker compose --env-file .env.runtime logs -f chromie-tts
```

Soridormi MCP 日志：

```bash
cd ../soridormi
docker compose -f compose.sim.yaml --profile mcp-runtime logs -f mcp-runtime
```

## 常见问题

### 找不到 Soridormi

```bash
./scripts/start_voice_mujoco.sh --soridormi-repo /absolute/path/to/soridormi
```

### MuJoCo viewer 没有打开

确认从 Linux 图形桌面终端启动，并且 `DISPLAY` 已设置。服务器环境使用 `--no-viewer`。

### 可以对话但没有动作

检查：

```bash
./scripts/status_voice_mujoco.sh
```

并查看 Soridormi MCP 日志。统一启动器会强制启用：

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

### 没有听到语音

运行：

```bash
python orchestrator/list_devices.py
```

然后在 `orchestrator/.env.local` 中指定正确的 `ORCH_OUTPUT_DEVICE`。
