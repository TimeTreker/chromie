# Chromie 中文指南

本文是中文入口，不重复维护完整配置、API 和操作命令。项目目标以
[PROJECT_CHARTER.md](PROJECT_CHARTER.md) 为准，当前状态以
[STATUS.md](STATUS.md) 为准，里程碑以 [ROADMAP.md](../ROADMAP.md) 为准。

## 项目目标

Chromie 是一个本地优先、实时、可中断、可审计的语音与具身技能控制平面。
它要完成的不是底层机器人控制，而是下面这条稳定闭环：

```text
自然语音
-> 确定性运行控制
-> 意图理解与规划
-> 严格校验的语音/命名技能请求
-> 可信执行
-> 成功、失败、取消或恢复状态
-> 简洁语音反馈
```

上层交互契约应同时适用于 MuJoCo 和未来实体机器人。语言模型不能看到或产生
原始电机、关节、力矩、执行器数组或总线命令。

## 职责边界

Chromie 负责：

- 麦克风、VAD、ASR 协调、TTS 播放和打断；
- stop、cancel、emergency、silence 等确定性路径；
- 对话状态、原生结构化 Agent 输出和严格契约；
- Agent Skills：由 Agent 按需选择的无执行权任务方法，帮助生成 Plan；
- Capability / Tool：通过可信 Runtime 和 Provider 执行的原子能力；
- 可信 Skill Runtime 的确认、调度、超时、取消和证据；
- 配置、验收与可复现开发制品工具。

Soridormi 负责：

- 具身规划和执行；
- MuJoCo 与实体 Provider；
- 机器人资源互斥、监控、停止、急停和恢复；
- 驱动、标定、状态估计与硬件投产。

`hardware/` 目录是旧的 mock 兼容服务，不是未来实体机器人的实现位置。

## 当前状态

可复现的本地标准测试门禁已经恢复：仓库策略、测试归属、Ruff、Mypy、文档、
1,662 个主要测试及 20 个旧 Agent 测试均已通过。当前第一优先级是保留与当前
源码一致的最小真实语音闭环证据：真实麦克风输入，经 ASR、Cognitive
Gateway、Goal-driven chat、TTS 到可听播放。在该证据和随后的完整目标证据
关闭前，除直接修复或明确的安全/来源阻塞外，不新增功能架构、运行开关或
术语。之后再继续当前版本的 Gateway/Core、取消和 MuJoCo 证据。仓库使用
`development` 作为中性开发身份，当前没有版本发布或公开分发计划。

已完成的开发基础包括：

- 原生严格 `/interaction`；
- Goal Association、Fast/Deep Planner、Response Composition 与统一主机协调器；
- 公共安全配置对 `chat,tool` 使用权威 `apply`，维护的 Soridormi 启动器在启用可信
  Provider 后把权威范围扩大到 `chat,robot_action,tool`；
- 请求绑定的口头确认与拒绝；
- Soridormi 命名技能；
- 打断、取消、停止与恢复；
- synthetic、virtual-mic、acoustic、supervised 四种语音验收工具，以及当前
  Goal-driven 文本到 MuJoCo 证据工具；
- 证据校验与 preview-only 开发制品打包工具。

RTX 5090 参考主机上的 GPU smoke、synthetic 七场景和 PipeWire virtual-mic
七场景均曾通过并保留历史证据。文本输入经旧 `/interaction` 路径、可信
Skill Runtime、Soridormi MCP 到 MuJoCo 的 walk/nod/turn 链路也有历史证据。
这些证据只对其记录的源码与旧语义路径有效，不能证明当前统一 Goal-driven
Runtime。仍须在干净、匹配的 Chromie 与 Soridormi checkout 上重新运行，
记录 `apply`、完成、`sim` 模式与 safe-idle 证据。

acoustic 模式使用 TTS 生成语音，通过主机扬声器播放并由配置的输入设备采集，
可以降低人工语音测试成本。真实人声、真实麦克风/扬声器支持声明和人工审核
需要单独完成 supervised 验收。现阶段不能宣称实体机器人支持。

## Agent Skills

Chromie 已接受 Agent Skills 架构：Agent 在自己的职责范围内，根据当前
Goal 和上下文选择零个、一个或多个 Agent Skills，并生成本次 Plan；Skill
只提供可复用方法和领域经验，没有独立 Goal、Provider 注册、权限或执行权；
Plan 最终仍只能通过 `capability_id` 调用已注册 Capability，并经过 Trusted
Capability Runtime（当前代码兼容名仍为 Trusted Skill Runtime）与
Provider/Soridormi 校验。

该架构已经实现：当前输出使用 `capability_id`，保留有界的历史
`skill_id` 读取；仓库拥有只读 Loader、模型选择、按 Agent 职责投影、Plan
provenance，以及 grounded external information 与 weather 两个方法包。真实
模型选择和 Provider-backed weather 仍需保留当前版本的目标证据。详见
[Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md) 和
[Agent Skills Implementation Plan](AGENT_SKILLS_IMPLEMENTATION_PLAN.md)。

## 开发主线

- **当前 Issue**：独立、严格的 `current-revision-live-voice` source-bound
  verifier profile 已实现并通过自动测试；下一步是在提交后的同一干净 revision
  上，用 supervised `speech-only` runner 保留一次真实麦克风到可听播放的通过
  证据和操作员听觉确认。
- **后续工程 Issue**：依次完成 broad exception 分类、Host typed settings、
  playback/input lifecycle 拆分、受支持配置组合收缩、按 package 扩大 Mypy、
  文档表面收缩。
- **开放证据 Issue**：保留统一 Goal-driven Runtime 的干净、来源绑定 live-text、
  active cancellation 和 MuJoCo safe-idle 证据。
- **取消证据**：named-goal 精确取消、Goal 状态原子协调和剩余确认令牌重建已
  实现；仍需补充受监督的 E-stop/safe-idle 及宽范围 reflex 协调证据。
- **实体准备**：选择一台实体参考机器人，先完成身份、安全、网络和无动作检查。
- **实体试点**：从无动作检查、单技能低速运行逐步进入受监督多技能任务。
- **语音设备证据**：需要真实麦克风/扬声器支持时，再单独完成 supervised
  语音验收与人工审核。
- **后续**：在基础闭环稳定后，再考虑视觉、长期记忆、复杂恢复和更高自治。

早期开发增量现在统一归入“实时交互基础”和“结构化具身基础”两项已完成能力，
不再使用顺序编号作为独立规划单位。语音验收使用功能化脚本名和
`.chromie/acceptance/voice/` 证据目录；文本到 MuJoCo 证据也只使用语义化名称。
当前工作的核心是用精确源码身份和执行证据证明受限的 MuJoCo 工程能力，再逐步
证明实体试点所需的安全、设备和 Provider 可替换性。

## 快速开始

```bash
cp .env.local.example .env.local
./scripts/show_profile.sh
BUILD=1 ./scripts/start_services.sh
./scripts/setup_orchestrator.sh
./scripts/start_orchestrator.sh
```

Chromie 会生成 `.env.runtime`，并写入一个被 Git 忽略的根目录 `.env`，
方便普通 `docker compose ...` 命令读取同一套变量。不要直接编辑这些
生成文件。

自动测试：

```bash
./scripts/run_tests.sh
```

完整启动、验收和恢复命令见
[CHROMIE_RUNBOOK.md](../CHROMIE_RUNBOOK.md)。环境变量见
[CONFIGURATION.md](CONFIGURATION.md)，接口见
[API_REFERENCE.md](API_REFERENCE.md)，证据等级见
[ACCEPTANCE.md](ACCEPTANCE.md)。

## 防跑偏原则

- 当前工程目标没关闭前，不用新功能掩盖证据缺口。
- Chromie 不实现实体机器人底层驱动。
- 不让 LLM 自我授权或绕过确认和安全策略。
- 仿真自动通过不等于目标设备验证，更不等于实体设备支持。
- 新能力必须说明所有者、失败语义、取消语义、证据等级和回滚方式。
