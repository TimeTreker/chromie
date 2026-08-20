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
- 可信能力运行时（Trusted Capability Runtime）的确认、调度、超时、取消和证据；
- 配置、验收与可复现开发制品工具。

Soridormi 负责：

- 具身规划和执行；
- MuJoCo 与实体 Provider；
- 机器人资源互斥、监控、停止、急停和恢复；
- 驱动、标定、状态估计与硬件投产。

`hardware/` 目录是旧的 mock 兼容服务，不是未来实体机器人的实现位置。

## 当前状态

可复现的本地标准测试门禁已经恢复。任何门禁声明都必须引用一次新的
`./scripts/run_tests.sh` 的精确输出，不在概览中维护容易过期的固定测试数量。
与当前源码一致的最小真实语音闭环 strict verifier 已实现；当前保留的物理输入
已经到达 VAD/ASR，但尚未产生包含要求含义的可理解语句，因此不能宣称物理语音
闭环已通过。当前优先级是完成不要求物理语音的
`source_bound_development` 证据闭环。在该证据关闭前，除直接修复或明确的
安全/来源阻塞外，不新增功能架构、运行开关或术语。仓库使用
`development` 作为中性开发身份，当前没有版本发布或公开分发计划。

已完成的开发基础包括：

- Host 驱动的 Gateway/Core/Planner 原生交互闭环；
- Goal Association、Fast/Deep Planner（含 Communicative Activity）与统一主机协调器；
- 公共安全配置使用统一权威 `apply` Runtime；维护的 Soridormi 启动器只是在注册可信
  body Provider 后增加其明确声明的 Capability，可执行范围由 typed Goal/Capability contract 决定；
- 请求绑定的口头确认与拒绝；
- Soridormi 命名技能；
- 打断、取消、停止与恢复；
- synthetic、virtual-mic、acoustic、supervised 四种语音验收工具，以及当前
  Goal-driven 文本到 MuJoCo 证据工具；
- 证据校验与 preview-only 开发制品打包工具。

RTX 5090 参考主机上的 GPU smoke、synthetic 七场景和 PipeWire virtual-mic
七场景均曾通过并保留历史证据。旧版本通过 Agent `/interaction`、可信
Skill Runtime、Soridormi MCP 到 MuJoCo 的 walk/nod/turn 链路也保留了历史证据；
该接口现已退休。那些证据只对其记录的源码与旧语义路径有效，不能证明当前统一
Goal-driven Runtime。仍须在干净、匹配的 Chromie 与 Soridormi checkout 上重新运行，
记录 `apply`、完成、`sim` 模式与 safe-idle 证据。

acoustic 模式使用 TTS 生成语音，通过主机扬声器播放并由配置的输入设备采集，
可以降低人工语音测试成本。真实人声、真实麦克风/扬声器支持声明和人工审核
需要单独完成 supervised 验收。现阶段不能宣称实体机器人支持。

## Agent Skills

Chromie 已接受 Agent Skills 架构：Agent 在自己的职责范围内，根据当前
Goal 和上下文选择零个、一个或多个 Agent Skills，并生成本次 Plan；Skill
只提供可复用方法和领域经验，没有独立 Goal、Provider 注册、权限或执行权；
Plan 最终仍只能通过 `capability_id` 调用已注册 Capability，并经过 Trusted
Capability Runtime（`CapabilityRuntime`）与 Provider/Soridormi 校验。
Chromie 的实时可执行合同只使用 `capability_id`；Soridormi 的 wire `skill_id`
仅在 adapter 边界翻译，Agent Skill 的 `agent_skill_id` 则属于独立认知命名空间。

该架构已经实现：当前输出和实时输入使用 canonical `capability_id`；仓库拥有只读 Loader、模型选择、按 Agent 职责投影、Plan
provenance，以及 grounded external information 与 weather 两个方法包。真实
模型选择和 Provider-backed weather 仍需保留当前版本的目标证据。详见
[Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md) 和
[Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md)。

## 开发主线

- **当前架构基线**：主 authority seam 已固定为 `Goal Interpretation →
  Responsibility evidence → Fast Planner 快速推进 →（可立即执行的安全 Activity）
  和/或 Goal Association / Deep Planner continuation → 需要持久连续性时建立
  Canonical Goal → canonical planning → Work/Primary Activity → realization → Provider
  → Evidence`。GI 的 Fast/Deep 只有认知深度/上下文/推理预算差异，authority 和输出
  相同；均不得写回复文本、创建 Work/Activity、选择 lane/Capability/Plan。Fast
  Planner 是第一个 HOW owner，但 GA 仍唯一拥有 canonical Goal continuity。
- **下一阶段设计**：Epistemic Qualification 只负责“证据是否足以建立某个事实”，
  Forward Adaptation 只允许有界的未来认知上下文；二者都不是新的 owner。在线
  Reflection 不得修改共享 Fast/Deep 策略、Stable Mind、全局 prompt/model、授权或
  Capability 语义，也不得学习 phrase→Capability / pattern→always-or-never-Deep
  这种 shortcut。
- **当前 Issue**：完成默认 `source_bound_development` 证据闭环；保留与当前
  revision 绑定的 Gateway/Core、Agent Skill 与 weather、Social Attention、
  配对 MuJoCo 以及第二台机器 LAN 证据。
- **开放证据**：干净的 live-text、active cancellation、MuJoCo safe-idle、
  人工语义审核和来源身份必须按目标 profile 一起判断，历史成功不能代替当前证据。
- **已完成工程边界**：Host typed settings、playback/input lifecycle、受支持配置
  收缩和文档表面收缩已经实现。Mypy 仍保持最后一个实际通过的四文件增量基线；未经依赖完整环境验证的 package 级扩展已撤回，并作为独立清理工作等待整个新增范围先通过。
- **可选物理验证**：默认 profile 不要求物理语音或实体机器人。只有需要对应
  支持声明时，才运行 supervised 麦克风/扬声器或实体机器人验收。
- **实体准备与试点**：未来选择参考机器人后，从身份、安全、网络和无动作检查，
  再逐步进入受监督的低速单技能与多技能任务。
- **后续产品能力**：只有基础证据闭环稳定后，才评估视觉、复杂恢复和更高自治。

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
