# Chromie 项目指南

> 本文以仓库基础快照 `8c448e2de2cd8a602b0d48e31461f9be9f1b8d08` 为起点，
> 校验日期为 2026-06-13。验收与发布工具会记录实际应用补丁后的精确 commit。
> 当前工程里程碑是 **M13：原生结构化交互 Agent 与端到端语音验收**。
> 实时状态以 [`STATUS.md`](STATUS.md) 为准，里程碑定义以
> [`../ROADMAP.md`](../ROADMAP.md) 为准。

## 1. 项目定位

Chromie 是一个本地优先、GPU 加速的实时语音交互与具身技能编排平台。
它把语音识别、快速路由、语言模型推理、语音合成、短期会话状态、
可信技能运行时以及 Soridormi 机器人运行时组合成一条可中断、可追踪、
默认拒绝高风险动作的交互链路。

当前项目已经明显超过早期 M5/M6 阶段。M6-M12 的主要结构已经实现并有
自动化测试；M13 尚未关闭的重点是：

1. 原生 `/interaction`、严格校验和显式兼容回滚已经实现；
2. 完整、不可跳过且与请求绑定的语音确认对话尚未闭环；
3. 七项麦克风/MuJoCo 引导式验收和证据校验工具已经实现，但尚未在参考主机上
   生成并审核真实证据包；
4. `0.1.0-alpha.1` 候选版本、兼容性声明和打包工具已经准备，但在 M13 阻塞项
   关闭前不能作为可发布产物。

“已实现”“有自动测试”“已在目标设备验证”“可发布”是四个不同状态，不能
用一个“完成”概括。详见 [`STATUS.md`](STATUS.md)。

## 2. 当前架构

```text
主机：麦克风 / VAD / 播放 / 打断 / 会话状态 / Skill Runtime
  |
  +--> chromie-asr      WebSocket :9001  完整语句 PCM -> final 文本
  +--> chromie-router   HTTP      :8091  规则/LLM 路由
  +--> chromie-agent    HTTP      :8092  AgentResult / InteractionResponse / TaskGraph
  +--> chromie-tts      WebSocket :5000  文本 -> 流式 PCM
  +--> chromie-llm      HTTP      :11434 Ollama
  +--> Soridormi MCP    HTTP      :8000  命名具身技能、仿真与硬件安全
```

Docker 中运行五个模型/服务组件；主机 Orchestrator 直接管理音频设备和实时
交互。Soridormi 是独立部署的具身执行与安全边界。

`hardware/daemon.py` 只是旧兼容链路的模拟硬件服务。当前实现始终构造
`MockRobotDriver`；仓库中存在串口相关名字或文件并不表示已经选择或验证了
真实串口驱动。

## 3. 两条交互路径

### 3.1 结构化路径

```text
麦克风 -> 主机 VAD -> ASR -> 确定性运行控制
  -> Agent /interaction -> 严格 InteractionResponse
  -> InteractionCoordinator -> Skill Runtime
      -> chromie.speak -> TTS -> 播放
      -> Soridormi 命名技能 -> MCP -> MuJoCo / 机器人
```

启用：

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

当前 `/interaction` 是真实可用的严格 API，并默认使用原生结构化输出。
各专用 Agent 在执行过程中直接累积 `InteractionSpeech` 与 `SkillRequest`，完成后
再次按共享 schema 校验；不再先生成完整 `AgentResult` 再转换。旧适配器仅保留为
显式回滚模式，原生校验失败时默认 fail closed，只有开启
`AGENT_NATIVE_INTERACTION_FALLBACK=1` 才会回退。

### 3.2 兼容路径

```text
ASR -> Router -> Agent /run -> AgentResult
  -> 兼容语音/动作 -> TTS / 可选模拟硬件 daemon
```

该路径用于回归和渐进迁移。命名技能失败时，不能回退成未经验证的低级硬件动作。

### 3.3 纯对话回退

关闭 Router 或兼容服务异常时，可以走：

```text
ASR -> Ollama -> TTS -> 播放
```

此回退只能生成语音，不获得技能或硬件权限。

## 4. 安全与所有权边界

- Router 只做路由，不执行副作用。
- Agent 只产生经过 schema 验证的语音、命名技能请求、兼容结果或 TaskGraph。
- Orchestrator 负责音频、打断、短期会话状态和可信 Skill Runtime。
- Skill Runtime 负责注册表解析、可用性、确认、超时、并发、互斥、取消与 trace。
- Soridormi 负责机器人计划、执行、跨进程资源互斥、监控、停止、急停和硬件投产。
- 语言模型不是最终授权者。

`InteractionResponse` 会递归拒绝已知低级字段，例如原始关节目标、马达命令、
执行器控制和力矩命令，即使它们藏在嵌套参数或 metadata 中也会失败。

## 5. 服务说明

### ASR

- WebSocket 默认端口 `9001`；
- 主机发送一个完整语句的 PCM16、单声道、通常 16 kHz 二进制帧；
- 服务返回一个 `final` JSON；
- 当前没有 partial transcript；
- 语句切分和 barge-in 由主机 VAD 负责。

详见 [`../asr/README.md`](../asr/README.md)。

### Router

- HTTP 默认端口 `8091`；
- 支持 `rules_only`、`hybrid`、`llm_only`；
- 停止、打断等运行控制应优先保持确定性；
- `RouteDecision` 只是控制面建议，不等于执行授权。

详见 [`../router/README.md`](../router/README.md)。

### Agent

- HTTP 默认端口 `8092`；
- `/run` 返回兼容 `AgentResult`；
- `/interaction` 返回严格 `InteractionResponse`；
- 提供 Capability Registry 和 TaskGraph API；
- 不访问麦克风、扬声器、MCP 或硬件。

详见 [`../agent/README.md`](../agent/README.md)。

### TTS

- WebSocket 默认端口 `5000`；
- 返回 `start` JSON、若干二进制 PCM chunk、`end` JSON；
- 一个进程内的 OuteTTS/llama.cpp 模型状态是可变的，生成实际串行化；
- `TTS_MAX_LENGTH` 是生成 token 预算，不是文本字符限制；限制文本应使用
  `TTS_MAX_TEXT_CHARS`。

详见 [`../tts/README.md`](../tts/README.md)。

### Orchestrator

- 在主机运行；
- 负责音频设备、VAD、播放、打断、会话状态和技能执行协调；
- 状态保存在内存中，重启后不持久；
- 每个语句有 SID，多轮共享 `conversation_id` 直到重置或过期。

详见 [`../orchestrator/README.md`](../orchestrator/README.md)。

## 6. Capability Registry、Skill Registry 与 TaskGraph

### Agent Capability Registry

Agent 启动时加载静态 manifest，用于 TaskGraph 规划、验证、策略和 MCP 调用。
当前 Soridormi 快照包含 4 个 agent、12 个 tool，并固定到上游 commit：

```text
a092dc704f1ab797fb1d4f542696fe75026eb171
```

manifest 缺失、格式错误、环境变量未解析或标识符重复会使 Agent 启动失败。
详见 [`agent_capability_registry.md`](agent_capability_registry.md)。

### 主机 Skill Registry

Orchestrator 的 Skill Registry 注册运行时 provider，例如：

- `chromie.speak` 本地语音技能；
- 从 Soridormi 在线目录加载的命名具身技能。

它和 Agent Capability Registry 目标相关但不是同一个内存对象。M13 原生 Agent
必须连接两者的语义，而不能绕过主机执行策略。

### TaskGraph

已经实现：验证、dry-run、只读执行、planning-only 执行、受保护副作用执行、
图绑定一次性确认 grant、取消、trace、调度状态和有限并发。

所有实际执行开关默认关闭：

```env
AGENT_ENABLE_TASK_GRAPH_PLANNING=0
AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION=0
AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=0
AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION=0
AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION=0
AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION=0
```

LLM 规划出的图不会自动执行。物理节点即使开启并发也保持串行，并需要确认、
活动监控和急停 fallback。详见 [`agent_task_graph.md`](agent_task_graph.md)。

## 7. 环境准备

推荐 Linux + NVIDIA GPU + Docker Compose + NVIDIA Container Toolkit。
Orchestrator 推荐 Python 3.11 Conda 环境。

```bash
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh
cp orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

在 `orchestrator/.env.local` 中显式设置输入和输出设备。

查看自动选择的硬件 profile：

```bash
./scripts/detect_hardware_profile.sh
./scripts/show_profile.sh
```

生成的 `.env.runtime` 不应手工长期维护。优先级和全部环境变量见
[`CONFIGURATION.md`](CONFIGURATION.md)。

## 8. 启动

启动 Docker 服务：

```bash
./scripts/start_services.sh
```

启动主机 Orchestrator：

```bash
./scripts/start_orchestrator.sh
```

开发时手动启动：

```bash
./scripts/build_runtime_env.sh
python -m orchestrator.orchestrator
```

必须从仓库根目录以模块方式运行，不要在 `orchestrator/` 内直接执行脚本。

## 9. 验证层级

Chromie 把证据分为四层：

1. **自动化测试**：合同、策略、调度、取消和控制面；
2. **服务/GPU smoke**：容器、CUDA、模型加载与简单推理；
3. **在线仿真验收**：真实 Soridormi MCP/MuJoCo；
4. **受监督硬件验收**：真实设备上的确认、监控、停止和恢复。

运行自动化测试和文档一致性检查：

```bash
./scripts/run_tests.sh
```

GPU smoke：

```bash
./scripts/gpu_smoke_test.sh
```

结构化文本到在线 Soridormi 验收：

```bash
./scripts/interaction_text_acceptance.py
```

该脚本验证 Router、原生 `/interaction`、严格合同、Skill Runtime、在线
Soridormi MCP 和测试语音 scheduler；它不证明真实麦克风、真实 TTS 播放或硬件动作。

M5 受监督目标验收：

```bash
SUPERVISED_ACCEPTANCE=1 ./scripts/m5_target_acceptance.sh
```

此流程会故意把 Soridormi 留在急停状态，必须按 runbook 完成显式恢复。
完整说明见 [`ACCEPTANCE.md`](ACCEPTANCE.md) 和
[`../CHROMIE_RUNBOOK.md`](../CHROMIE_RUNBOOK.md)。

## 10. M13 完整麦克风验收矩阵

先提交候选 revision，再在参考主机和受监督的 MuJoCo-backed Soridormi 上运行。
工具默认拒绝脏工作区；`--allow-dirty` 只用于探索性证据，不能满足正式发布门槛：

```bash
python scripts/m13_voice_acceptance.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi
```

该工具会按顺序引导并记录七项：纯语音、语音加命名技能、拒绝、barge-in、
具身技能取消、显式 stop、会话 follow-up。证据目录包含：精确 commit、脱敏后的
运行环境、音频设备、JSONL 会话事件、Orchestrator 日志、录音、自动检查以及
操作员结论和备注。

完成后执行：

```bash
python scripts/verify_m13_evidence.py --require-clean \
  .chromie/acceptance/m13/<验收编号>
```

dry-run 只能演练命令，不能作为目标证据。除此之外，仍需单独实现和验证不可跳过、
与请求绑定的语音确认对话。在真实证据包通过并完成隐私、安全空闲与恢复审核前，
不应把 M13 标记为完成。

## 11. 已知限制

- `/interaction` 已默认原生输出，旧适配器只用于显式回滚；
- 非跳过式、请求绑定的语音确认尚未完整闭环；
- 会话、trace、grant 和 scheduler 状态主要是进程内存；
- Agent 与 Orchestrator 的资源仲裁器不是分布式锁；
- Jetson profile 是配置起点，不等于完整 ARM64 镜像和目标证据；
- legacy hardware daemon 只使用 mock driver；
- 已有 `0.1.0-alpha.1` 候选说明、兼容性文件和打包工具，但当前没有正式
  GitHub Release、预构建镜像或稳定升级承诺。


## 12. Alpha 候选发布

候选版本写在仓库根目录 `VERSION`，发布说明和兼容性声明位于 `release/`。
在 M13 阻塞项尚未关闭时，只允许生成不可发布的预演包：

```bash
python scripts/prepare_alpha_release.py --preview \
  --evidence-dir .chromie/acceptance/m13/<验收编号>
```

正式生成命令会要求：真实证据通过、工作区干净、没有剩余 closure blocker，
并重新运行全部测试。输出包含源码归档、manifest、测试日志和 SHA-256 校验值，
但工具不会自动创建或推送 Git tag。

## 13. 文档治理

状态、API、环境变量、里程碑或安全边界变化必须在同一变更中更新文档。

```bash
python scripts/check_docs.py
```

文档入口见 [`README.md`](README.md)。发布范围和检查表见
[`RELEASE.md`](RELEASE.md)。
