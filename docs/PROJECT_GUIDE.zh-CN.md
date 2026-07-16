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
- 可信 Skill Runtime 的确认、调度、超时、取消和证据；
- 配置、验收与发布工具。

Soridormi 负责：

- 具身规划和执行；
- MuJoCo 与实体 Provider；
- 机器人资源互斥、监控、停止、急停和恢复；
- 驱动、标定、状态估计与硬件投产。

`hardware/` 目录是旧的 mock 兼容服务，不是未来实体机器人的实现位置。

## 当前状态

当前重点是 **在统一 Goal-driven Runtime 与单一语义权威边界上重新保留
当前版本的语音及文本到 MuJoCo 证据**。`0.0.1` 仍是被阻塞的候选版本，尚未
发布。Chromie 是真实的主机控制平面；候选范围中的“sim”只表示 Soridormi
使用 MuJoCo `sim` 模式执行机器人动作，不代表实体机器人支持。

已完成的 `0.0.1` 基础包括：

- 原生严格 `/interaction`；
- Goal Association、Fast/Deep Planner、Response Composition 与统一主机协调器；
- 公共安全配置对 `chat` 使用权威 `apply`，维护的 Soridormi 启动器在启用可信
  Provider 后把权威范围扩大到 `chat,robot_action`；
- 请求绑定的口头确认与拒绝；
- Soridormi 命名技能；
- 打断、取消、停止与恢复；
- synthetic、virtual-mic、acoustic、supervised 四种语音验收工具，以及当前
  Goal-driven 文本到 MuJoCo 证据工具；
- 证据校验与 `0.0.1` 发布打包工具。

RTX 5090 参考主机上的 GPU smoke、synthetic 七场景和 PipeWire virtual-mic
七场景均曾通过并保留历史证据。文本输入经旧 `/interaction` 路径、可信
Skill Runtime、Soridormi MCP 到 MuJoCo 的 walk/nod/turn 链路也有历史证据。
这些证据只对其记录的版本和旧语义路径有效，不能证明当前统一 Goal-driven
Runtime。发布前仍须在干净、匹配的 Chromie 与 Soridormi checkout 上重新运行，
记录 `apply`、完成、`sim` 模式与 safe-idle 证据。
acoustic 模式使用 TTS 生成语音，通过主机扬声器播放并由配置的输入设备采集，
可以降低人工语音测试成本。真实人声、真实麦克风/扬声器支持声明和人工审核
不再阻塞 M13 文本交互闭环，但如果要发布“真实语音设备”支持声明，仍需要单独
完成 supervised 验收。现阶段不能宣称实体机器人支持。

## 开发主线

1. **当前**：完成当前版本的自动测试，并保留统一 Goal-driven Runtime 的干净
   语音和文本到 MuJoCo 证据，之后才可解除 `0.0.1` 候选发布阻塞。
2. **实体准备**：选择一台实体参考机器人，先完成身份、安全、网络和无动作检查。
3. **实体试点**：从无动作检查、单技能低速运行逐步进入
   受监督多技能任务。
4. **语音设备证据**：如果要发布真实麦克风/扬声器支持声明，再单独完成 supervised
   语音验收与人工审核。
5. **后续**：在基础闭环稳定后，再考虑视觉、长期记忆、复杂恢复和更高自治。

原 M0-M12 只是历史开发增量，现在合并为“实时交互基础”和“结构化具身基础”
两项已完成能力，不再作为独立规划单位。新的语音验收使用功能化脚本名和
`.chromie/acceptance/voice/` 证据目录；旧 M13 只作为历史文本证据名称保留。
这条顺序的核心是：先用当前版本的精确来源与执行证据证明受限的 `0.0.1`
候选范围，其机器人执行证据限定在 Soridormi 的 MuJoCo `sim` 模式；发布后再
继续证明实体试点所需的安全、设备和 Provider 可替换性，最后接入实体机器人。

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

- 当前 milestone 没关闭前，不用新功能掩盖证据缺口。
- Chromie 不实现实体机器人底层驱动。
- 不让 LLM 自我授权或绕过确认和安全策略。
- 仿真自动通过不等于目标设备验证，更不等于可发布。
- 新能力必须说明所有者、失败语义、取消语义、证据等级和回滚方式。
