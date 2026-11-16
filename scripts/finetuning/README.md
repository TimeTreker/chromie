# Gemma 4 本地微调工具

Owner: offline experience-to-ability tooling. Audience: Chromie maintainers
curating local training data and qualifying an explicitly selected model candidate.
This component README owns executable commands; the existing
[experience learning document](../../docs/EXPERIENCE_TO_ABILITY_LEARNING.md)
owns promotion policy. No new Runtime authority, route, profile or behavior switch.

## 当前源码与模型身份

本工具按 `main` 的 `55f5587d4ca8034fdefb24e53d632df5790b7dba` 实现。
Planner 只决定 Work HOW、参数和通信需要；Social Cognition 决定是否、何时以及如何交流。
UMI/GA 的 WHAT、Goal 连续性、Runtime 确认/取消、Soridormi 执行与安全权责不变。

真实路径是 `CognitiveWorkRequest` / `SocialCognitionRequest` → 当前投影和提示词
→ 当前动态 Schema → 模型原始 JSON → 生产解析、DTO 和 resolver 校验。
工具不实例化 `CapabilityRuntime`，不执行身体动作，不写 Memory，不修改在线提示词。
resolver 回放不是 Host dispatch、听到语音或物理效果的证据。

RTX 5090 的现有配置是 SGLang，而不是 Ollama：

- `env/profiles/rtx5090.env`：所有认知角色共用 `chromie-gemma4-12b`。
- `docker-compose.sglang.yml`：`google/gemma-4-12B-it`，固定 revision
  `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`，在线 FP8，64K serving context。
- 官方配置：`Gemma4UnifiedForConditionalGeneration` / `gemma4_unified`，11.95B
  稠密 Unified 模型，48 层，hidden size 3840，词表 262144，1024 sliding window，
  每六层一层 full attention；原生上下文 262144，不代表 32GB 卡可训练这么长。
- full attention 使用 K=V，其 `v_proj` 为 None。当前结构只有 184 个 Q/K/V/O
  attention 投影可注入，而不是把所有层都按四个线性层处理。
- 模型卡标明 Apache-2.0。分发时附完整许可证，保留适用声明与 NOTICE，并标明修改；
  具体条件见 [Google 提供的许可证原文](https://ai.google.dev/gemma/apache_2)。
  这是模型许可身份记录，不代表用户数据、第三方数据也获得了训练或发布许可。

身份来源和文件 SHA256 在 [model.lock.json](model.lock.json)。配置、模板、tokenizer 和
23.9GB 权重均验证到上述 revision；别名、大小字符串或本地目录名都不能替代身份。
[官方模型卡](https://huggingface.co/google/gemma-4-12B-it/blob/707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7/README.md)、
[Transformers 架构](https://huggingface.co/docs/transformers/model_doc/gemma4_unified)。

采用 Transformers + PEFT + bitsandbytes NF4 QLoRA；标准 BF16 LoRA 作为显式选项。
不需要 TRL：这里的训练目标是精确 JSON completion，直接保留生产消息和自定义损失掩码更容易审计。
[PEFT 量化说明](https://huggingface.co/docs/peft/developer_guides/quantization)。
Unsloth 官方也声明支持 Unified 12B，但本实现不额外引入其模型补丁和独立模板；要改用它，
必须另做同基座、同语料、同模板与同验证合约的对照。
[Unsloth 说明](https://unsloth.ai/docs/models/gemma-4/train)。
不把 Ollama/GGUF 或已经 FP8/QAT 量化的服务权重当作 HF 训练基座，也不假设此架构可以直接
通过 Ollama `ADAPTER` 导入。未来 Ollama 路径需单独核实转换、模板、量化和全部角色的结果。

## 安装、联网准备与离线运行

目标 Ubuntu 26.04 + RTX 5090 32GB。使用隔离的 Python 3.12 环境，避免系统 Python
版本和训练轮子不匹配；宿主 NVIDIA 驱动必须能运行所安装 PyTorch 的 CUDA 版本。
启动前以 `preflight --gpu` 实测 sm120、BF16、NF4 前向/反向，不根据版本字符串猜测支持。
本会话没有可用 NVIDIA 驱动或完整权重，因此没有声称完成 GPU 训练或显存验证。

以下均在仓库根目录执行。联网准备只下载公开依赖和明确 revision 的模型，不上传交互数据：

```bash
conda create -y -p "$PWD/.chromie/venvs/finetuning" python=3.12
conda activate "$PWD/.chromie/venvs/finetuning"
python -m pip install -r requirements-test.txt -r scripts/finetuning/requirements.txt
mkdir -p .chromie/finetuning
chmod 700 .chromie/finetuning
hf download google/gemma-4-12B-it \
  --revision 707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7 \
  --local-dir .chromie/finetuning/base
python -m pip freeze > .chromie/finetuning/environment.lock.txt
python -m pip download -r .chromie/finetuning/environment.lock.txt \
  -d .chromie/finetuning/wheels
```

隔离机器使用同 OS/架构/Python 的 wheelhouse 安装：
`python -m pip install --no-index --find-links .chromie/finetuning/wheels -r .chromie/finetuning/environment.lock.txt`。
预先保存现有 SGLang 镜像；这个训练环境不安装到在线 Agent 镜像里。
磁盘建议预留至少 100GB，CPU 合并 BF16 权重建议至少 64GB RAM；这是容量规划，非实测峰值。
准备完成后可以断网。所有工具命令都强制本地文件加载、HF offline、禁用 Hub telemetry，
不使用 WandB、Hub push 或远程评测；评测 URL 只接受 loopback HTTP，客户端不采用代理。

## 数据边界与人工审核

读取已有 `chromie.llm_call_evidence` v1 JSONL，也支持带 Docker/日志前缀的
`llm_call_evidence {...}`。它来自 `shared/chromie_runtime/llm_diagnostics.py`，包含
精确请求、动态 Schema、原始输出及 provider 完成状态。普通 Runtime Trace 只有时间、
跨度和有界属性，不能独自生成 SFT：只按 trace_id 或唯一的 turn/session correlation
关联回执，保留摘要身份；没有 Trace 时标记 `trace_coverage=unavailable`。
截断、取消、不完整 stream、隐藏思考、Schema 失败、重复 JSON 键和 NaN 都拒绝。
原回执保留 Schema 属性顺序，不能用排序 JSON 重写：native decoder 的成员顺序有实际影响，
工具还单独绑定有序 Schema hash。已被重排的日志应重新采集，不能冒充精确生产回执。
need-first 首次 stream 被提前关闭时的部分回执也拒绝，不能当成完整计划训练。

必须保留模型调用前的原始 DTO、三种能力快照（all/common/index）、num_ctx 和
num_predict；它们由已有 episode/debug evidence 的可信来源提供并审核。
回执本身没有完整 DTO，缺失时无法无损还原。不要从输出计划反推输入，不要猜缺失 Goal、
Memory、Evidence 或参数来源，也不要为了通过校验而伪造快照。

先仅查看摘要身份：

```bash
python -m scripts.finetuning inspect .chromie/private/agent.log
openssl rand -out .chromie/finetuning/split.salt 32
chmod 600 .chromie/finetuning/split.salt
```

将 `reviews.json` 保存为数组，每个元素表示完整的一次 resolver 事务，多次调用保持原序。
这是字段示意；`request` 必须替换为对应版本真实 DTO，不能用这个空对象训练：

```json
[
  {
    "status": "pending_human_review",
    "reviewer": "local-reviewer",
    "privacy_approved": false,
    "semantic_approved": false,
    "training_eligible": false,
    "split": "frozen_test",
    "conversation_group": "same-complete-conversation",
    "contrast_group": "same-material-scenario-family",
    "language": "zh",
    "category": "evidence_truthfulness",
    "receipt_sha256": ["HASH_FROM_INSPECT"],
    "trace_sha256": [],
    "sanitized_sha256": "HASH_AFTER_REDACTION_REVIEW",
    "transaction": {
      "role": "social_cognition",
      "variant": "interaction",
      "request": {},
      "catalog": {"all": [], "common": [], "index": []},
      "settings": {"num_ctx": 65536, "num_predict": 4096}
    }
  }
]
```

支持角色/变体：Planner `canonical`（primary、Evidence re-entry、need-first 的完整调用链）、
`streaming`；Social Cognition `interaction`（primary 与一次 source-only deep continuation）、
`startup`。不从最终 canonical plan 或最终播报文本生成目标：每个 SFT 目标是该次原始 JSON，
SC 的记忆提议、need coverage、scope 和 Planner 的 Work/参数来源都用当次合约校验。

`redactions.json` 是 `[ {"from":"需要移除的精确原文", "to":"一致的非识别性替代值"} ]`，
没有需要替换的内容也必须明确提供 `[]` 并审核。它一致处理消息、Schema、目标和原始 DTO。
引用 span、token 位置、标识关联可能随替换改变；工具会重建提示词并回放校验，失配就拒绝，
不得丢弃 provenance 检查来容纳脱敏。应优先用不含个人信息的审核合成场景。

```bash
python -m scripts.finetuning export \
  --receipts .chromie/private/agent.log \
  --reviews .chromie/private/reviews.json \
  --redactions .chromie/private/redactions.json \
  --salt-file .chromie/finetuning/split.salt --preview-hashes
```

人工核对完整脱敏输入和目标之后，将对应 hash 写回 `sanitized_sha256`，设置
`status=approved`、`privacy_approved=true`、`semantic_approved=true`。
训练项还必须 `training_eligible=true` 且 `split=train`。失败答案需单独审核纠正的来源，
不能仅因日志写着 accepted 就视为正确。没有任何默认批准或自动训练晋升。

```bash
python -m scripts.finetuning export \
  --receipts .chromie/private/agent.log \
  --traces .chromie/private/runtime_trace.json \
  --reviews .chromie/private/reviews.json \
  --redactions .chromie/private/redactions.json \
  --salt-file .chromie/finetuning/split.salt \
  --output .chromie/finetuning/dataset-v1
```

若无 Trace，省略 `--traces` 并在 review 中保留空 trace 列表；存在相关 Trace 必须绑定其完整
JSON 的规范化 SHA256，`inspect` 回执摘要和各产物身份使用相同的排序键规范化 JSON。
输出是每事务一份 `cases/*.json`、train/validation/frozen_test JSONL 以及冻结清单。
目录 0700、文件 0600，拒绝覆盖已有输出。仅保留审核摘要、不输出原日志的其他字段。
电话/邮箱/密钥/用户目录扫描只是泄漏兜底，不能发现任意人名、地址、自由文本秘密；
人工隐私审核不可省。盐保存在本机；对话与 contrast group 用 HMAC 表示。

整个对话、contrast set、同一来源回执及相同输入不得跨 split，跨 split 冲突直接拒绝。
先选固定 split 再审核；不要按调用随机拆开同一对话，不要移动冻结测试项去训练。
仓库已有 qualification / everyday / model_limited 语料和它们的答案默认只用于评估，
包括名为 train_candidate 的历史资料也不自动获得训练资格。

冻结集至少覆盖中英、primary/streaming/re-entry、need-first、确认/取消、无能力、
多 Goal、Evidence 真伪/范围、信息来源、延迟/顺序、SC 沉默/交流/深层委托与 Memory 隐私。
保留安全允许/拒绝、已完成/尚未完成、看见/没看见、明确参数/歧义等单条件 contrast。
本补丁的测试数据是合约工具测试，不是完成语义审核的真实训练集。

## RTX 5090 训练

先记录原运行镜像/配置并按运行手册暂停当前语音/模型工作负载，腾出 GPU；工具不会自动停止服务。
32GB 卡不能同时容纳现有 64K SGLang 和训练。核实独占训练窗口后执行：

```bash
python -m scripts.finetuning preflight --base .chromie/finetuning/base --gpu
python -m scripts.finetuning audit-tokens \
  --base .chromie/finetuning/base --dataset .chromie/finetuning/dataset-v1 --max-length 8192
python -m scripts.finetuning train \
  --base .chromie/finetuning/base --dataset .chromie/finetuning/dataset-v1 \
  --role planner --method qlora --max-length 8192 --max-steps 2 \
  --output .chromie/finetuning/planner-smoke --accept-apache-2
```

默认 NF4 + double quant、BF16 compute、attention-only rank 8/alpha 16/dropout .05，
microbatch 1、accumulation 16、checkpointing、SDPA、学习率 5e-5、默认 200 steps。
冻结 embedding、lm_head、音频与视觉投影。对全部输入前向，只对 completion 的预测位置计算
262K 词表 logits 和 CE，避免给长提示词计算无损失的巨大 logits；保留原模型 softcap。
官方非思考 generation prefix 的空 thought channel 与已完成 assistant 模板不同，
工具验证两种渲染后对齐，mask 掉 system/user/prefix，只训练 JSON 和 end-of-turn。

默认完整长度上限 8192；不静默截断、不跳过长样本。最小真实测试样例实测约 Planner 4796、
SC 6450 tokens；带动态上下文的请求会更长。先根据 token audit 明确审核短上下文集合；
8K/16K 是否能训练仍需该 GPU 的两步 smoke 和实测峰值，不能保证无 OOM。
`--max-length 16384` 是显式实验上限，不代表已证明 32GB 可承载。不要裁掉必需事实来降低长度。
`--method lora` 使用 BF16 基座，32GB 更紧张，优先 QLoRA。OOM 时重启独立训练进程，
保留失败记录并缩小审核过的 cohort；不要把失败 run 当作完整 adapter。

smoke 后用新目录正式训练，例如 `--role social_cognition --max-steps 200`。
`--role both` 会混合两个角色，但部署成一个共享基座会影响所有角色，必须评估全部角色。
分别训练的两个 adapter 不会被工具自动叠加。每个选定角色必须同时有 train 和 validation。
冻结集不进入 loss。每个 run 绑定源码、语料、基座、实际依赖、seed、目标模块和 GPU 峰值；
只有有限 validation loss、源码未变并成功保存后才有 `run.completed.json`。

CPU 合并回原始 BF16 基座，不能对训练中的 NF4 权重直接当作部署成品：

```bash
python -m scripts.finetuning merge \
  --base .chromie/finetuning/base --run .chromie/finetuning/planner-smoke \
  --output .chromie/finetuning/merged-candidate --accept-apache-2
```

合并校验 adapter hash、基座身份，`safe_merge=True`；复制原 tokenizer/processor 元数据。
产物始终 `promotion_allowed=false`。SFT/合并成功、loss 降低都不等于能力改善。

## 基线、候选与退化检查

同一冻结语料和源码上，先对原 SGLang（30000）跑完整基线；再停原 engine，使用原固定镜像
与原 64K/FP8/scheduler/parser 参数，在 30001 起单独命名的候选。
不要并行跑两个 12B engine 来比较单卡延迟。保存原 `docker inspect chromie-llm`
与生成配置，并用 `docker inspect chromie-llm --format '{{.Image}}'` 记录镜像身份。
`serve` 从 `docker-compose.sglang.yml` 读取当前全部参数，只替换本地权重路径、候选名和
loopback port，去掉远程 revision。复用 `llm/sglang/Dockerfile` 的现有 Unified/XGrammar
修补；不要换一个未经核实的公共镜像。先打印命令检查，再在已释放 GPU 的独立终端启动：

```bash
SGLANG_IMAGE_ID=$(docker inspect chromie-llm --format '{{.Image}}')
python -m scripts.finetuning serve --merged .chromie/finetuning/merged-candidate \
  --image "$SGLANG_IMAGE_ID"
python -m scripts.finetuning serve --merged .chromie/finetuning/merged-candidate \
  --image "$SGLANG_IMAGE_ID" --launch
```

原服务暂停前保存 `SGLANG_IMAGE_ID`，跨终端手动使用该固定值；命令拒绝可变镜像 tag 和原端口。
启动会核对 merged 文件清单，只读挂载权重，不停止或修改已有容器；Ctrl-C 或
`docker stop chromie-lora-candidate` 停止候选。记录两批相同 serving precision/参数和
独立 engine lifetime；训练量化 NF4 与推理 FP8 是不同阶段。

```bash
python -m scripts.finetuning evaluate \
  --dataset .chromie/finetuning/dataset-v1 --split frozen_test \
  --url http://127.0.0.1:30000/v1 --model chromie-gemma4-12b \
  --output .chromie/finetuning/baseline
python -m scripts.finetuning evaluate \
  --dataset .chromie/finetuning/dataset-v1 --split frozen_test \
  --url http://127.0.0.1:30001/v1 --model chromie-gemma4-12b-ft-candidate \
  --output .chromie/finetuning/candidate
```

工具先重建并核对精确提示词、动态 Schema、解码参数，候选只接收生产输入，不接收 target、
分类、rubric 或语义审核。保留原始传输、解析结果、resolver verdict、逐调用/逐案例延迟、
server identity 和源稳定性；安全/Schema/来源/传输失败立即停止，完整批次不得拼接补跑。
候选走了未冻结的不同分支时报告未覆盖/失败，不冒充该分支已合格。
省略 `--url/--model` 只做 reference replay，绝不能用它作为 native 模型能力基线。

完整输出由独立人工/独立评估者审核；`semantic-review.json` 字段示意：

```json
{
  "baseline_sha256": "BASELINE_SUMMARY_CANONICAL_JSON_HASH",
  "candidate_sha256": "CANDIDATE_SUMMARY_CANONICAL_JSON_HASH",
  "reviewer": "independent-human",
  "independent": true,
  "cases": {
    "CASE_HASH": {"candidate_acceptable": true, "regressed": false}
  }
}
```

```bash
python -m scripts.finetuning compare \
  --baseline .chromie/finetuning/baseline/summary.json \
  --candidate .chromie/finetuning/candidate/summary.json \
  --review .chromie/private/semantic-review.json --latency-ratio 1.2 \
  --output .chromie/finetuning/nonregression.json
python scripts/check_repository_policies.py
python -m pytest -q tests/test_finetuning.py tests/test_finetuning_training.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 4 \
  --evidence-dir .chromie/finetuning/workflow-reference
```

paired compare 要求两批真实、完整、相同源码/语料/顺序、逐项 Schema/resolver pass、
每项候选可接受且不退化，并约束逐项延迟（默认最多基线 1.2 倍，50ms 测量容差）。
按角色、语言、变体、类别分别保留失败数；任何硬失败或语义退化不能用平均分抵消。
原生模型跨重启/流量的 near-tie 变动已是项目已知问题：在相同空闲条件、全新 serving lifetime
上重复完整配对批次，检查结果与尾延迟，不能凭一次 loss 或单个例子晋升。

workflow replay 只是架构检查，已有 corpus 不含 SC/VJ，不能代替全角色模型评测。
另起隔离 Agent 指向候选 SGLang，使用现有配置加载方式，保持当前 UMI/GA/Planner/VJ/SC/
Attention/Activation/Skill/Reflection 提示词和预算；再对原模型与候选各跑一次完整 everyday
模拟器 cohort（不要 `--only-case`、`--allow-failures` 或恢复被跳过案例来凑通过率）：

```bash
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a \
  --evidence-dir .chromie/finetuning/level-a
python scripts/general_ability_acceptance.py --mode live-text \
  --scenario-root scenarios/everyday --agent-url http://127.0.0.1:8093 \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --evidence-dir .chromie/finetuning/everyday-candidate
```

必须人工判读每个完整 episode：Goal/参数/范围、确认、取消、安全、无部分执行泄漏、
Evidence 来源/真伪、说到和做到的时序、虚构能力、重复播报、Memory 隐私，以及中英/长期对话。
目标模型通过前不能改低 oracle、忽略安全失败或把新语料塞入冻结测试答案。
随后完成当前修订的监督语音和默认 target-evidence 门槛；本工具不会自动判定可发布。

## 主动启用与回滚

本补丁不修改 profile、生成 `.env.runtime`、Compose、提示词或在线路由。
候选只监听单独 loopback 端口；真实设备服务的停止、部署与重启均由操作者明确执行。
晋升前保存原镜像 digest、配置、基座 revision、模型/adapter/merged 清单和完整证据。
先通过上述所有门槛，再在已有 profile/Compose owner 按正常交付流程显式切换。
不要覆盖原 HF snapshot，不要覆盖 `chromie-gemma4-12b` 的模型目录或 Ollama tag。

回滚：停止独立候选 Agent/engine，按原运行手册启动保存的原镜像和原 profile，
恢复 30000 的原模型与所有角色的既有模型名，核对 `/health`、`/v1/models` 和 runtime identity，
运行 canonical checks 与 must-pass 验证。若从未晋升，原配置不需还原，只需恢复被暂停的服务。
训练和评测产物留在 `.chromie/`，不进入 Git；未经额外审核，不发布家庭语料、adapter 或原始回执。

新增维护面：一个离线组件 README；core reading path 不变，无新增在线配置选择。
配置 inventory 新增四个第三方库内部设置（DO_NOT_TRACK、HF_HUB_DISABLE_TELEMETRY、
TOKENIZERS_PARALLELISM、WANDB_DISABLED）；由本离线进程固定，不是 Runtime 的新功能开关。
合并维护机会是继续沿用 experience-to-ability 的现有晋升政策，不另建训练权威或自动学习循环。
