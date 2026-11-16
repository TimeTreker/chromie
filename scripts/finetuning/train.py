"""Completion-only PEFT LoRA/QLoRA on a verified local Gemma4 Unified snapshot."""
from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

from .common import Rejected, digest, loads, private_dir, source_identity, write_json
from .dataset import load_dataset
from .model import gpu_preflight, offline, tokenize_sample, verify_base


def attention_targets(model: Any) -> list[str]:
    text = model.config.text_config
    expected = set()
    for index, kind in enumerate(text.layer_types):
        projections = ["q_proj", "k_proj", "o_proj"]
        # Gemma4 Unified shares K=V in full-attention layers: v_proj is None.
        if not text.attention_k_eq_v or kind == "sliding_attention":
            projections.append("v_proj")
        expected.update(f"model.language_model.layers.{index}.self_attn.{name}" for name in projections)
    targets = {name for name, _ in model.named_modules()
               if ".language_model.layers." in name and name.rsplit(".", 1)[-1] in
               {"q_proj", "k_proj", "v_proj", "o_proj"}}
    if targets != expected:
        raise Rejected("unexpected_gemma4_attention_modules")
    return sorted(targets)


def completion_loss(model: Any, inputs: dict[str, Any]) -> tuple[Any, Any]:
    import torch
    labels = inputs["labels"]
    if labels.shape[0] != 1:
        raise Rejected("completion_logits_require_microbatch_one")
    positions = (labels[0] != -100).nonzero().flatten()
    if not positions.numel() or positions[0].item() < 1:
        raise Rejected("completion_target_positions_invalid")
    # 262K vocabulary: predict only positions immediately before target tokens,
    # preserving the model's actual tied head and final logit softcap.
    outputs = model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"],
                    logits_to_keep=positions - 1, use_cache=False)
    loss = torch.nn.functional.cross_entropy(outputs.logits.float().reshape(-1, outputs.logits.shape[-1]),
                                             labels[0, positions])
    return loss, outputs


def train(*, base: Path, dataset: Path, output: Path, role: str, method: str = "qlora",
          max_length: int = 8192, max_steps: int = 200, seed: int = 42) -> None:
    offline()
    identity = verify_base(base)
    hardware = gpu_preflight()
    manifest, cases = load_dataset(dataset)
    source = source_identity()
    if manifest["source"] != source:
        raise Rejected("dataset_source_changed_reexport_against_current_contract")
    if not 256 <= max_length <= 16384 or max_steps < 1 or role not in {"planner", "social_cognition", "both"}:
        raise Rejected("invalid_training_configuration")
    if method not in {"qlora", "lora"}:
        raise Rejected("unsupported_training_method")
    import torch
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoTokenizer, BitsAndBytesConfig, Gemma4UnifiedForConditionalGeneration,
                              Trainer, TrainingArguments, set_seed)

    set_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(str(base), local_files_only=True, trust_remote_code=False)
    roles = {"planner", "social_cognition"} if role == "both" else {role}
    rows: dict[str, list[Any]] = {}
    lengths: dict[str, list[int]] = {}
    for split in ("train", "validation"):
        samples = [loads(line) for line in (dataset / (split + ".jsonl")).read_text().splitlines() if line]
        selected = [row for row in samples if row["role"] in roles]
        if not selected or {row["role"] for row in selected} != roles:
            raise Rejected("each_selected_role_needs_train_and_validation")
        rows[split] = [tokenize_sample(tokenizer, row, max_length) for row in selected]
        lengths[split] = [len(row["input_ids"]) for row in rows[split]]
    # Never truncate or silently drop the difficult/long examples. Inspect lengths
    # first, curate an explicit short-context cohort, then scale after a smoke run.
    kwargs: dict[str, Any] = {"local_files_only": True, "trust_remote_code": False,
                              "dtype": torch.bfloat16, "device_map": {"": 0},
                              "attn_implementation": "sdpa"}
    if method == "qlora":
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16)
    model = Gemma4UnifiedForConditionalGeneration.from_pretrained(str(base), **kwargs)
    if method == "qlora":
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                                gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    model.config.text_config.use_cache = False
    # Scope to decoder attention only; never tune embeddings, output head, vision
    # or audio projectors. Inspect actual module names rather than guessing support.
    targets = attention_targets(model)
    model = get_peft_model(model, LoraConfig(
        task_type=TaskType.CAUSAL_LM, r=8, lora_alpha=16, lora_dropout=0.05,
        bias="none", target_modules=targets))
    trainable = [name for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not trainable or any("lora_" not in name or ".language_model.layers." not in name for name in trainable):
        raise Rejected("non_adapter_parameter_became_trainable")
    model.enable_input_require_grads()

    def collate(batch: list[dict[str, Any]]) -> dict[str, Any]:
        size = max(len(row["input_ids"]) for row in batch)
        return {key: torch.tensor([row[key] + [pad] * (size - len(row[key])) for row in batch])
                for key, pad in (("input_ids", tokenizer.pad_token_id), ("attention_mask", 0), ("labels", -100))}

    class CompletionTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            loss, outputs = completion_loss(model, inputs)
            return (loss, outputs) if return_outputs else loss

    private_dir(output)
    record = {"base": identity, "source": source, "dataset_sha256": digest(manifest),
              "hardware": hardware, "method": method, "role": role, "seed": seed,
              "max_steps": max_steps, "max_length": max_length, "lengths": lengths,
              "target_modules": targets, "training_case_ids": [case["id"] for case in cases
                  if case["split"] == "train" and case["transaction"]["role"] in roles],
              "status": "started", "promotion_allowed": False}
    write_json(output / "run.started.json", record)
    arguments = TrainingArguments(
        output_dir=str(output / "checkpoints"), per_device_train_batch_size=1,
        per_device_eval_batch_size=1, gradient_accumulation_steps=16,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        bf16=True, tf32=True, learning_rate=5e-5, lr_scheduler_type="cosine", warmup_ratio=0.05,
        max_steps=max_steps, max_grad_norm=1.0, optim="adamw_torch", weight_decay=0.0,
        logging_steps=1, eval_strategy="steps", eval_steps=min(50, max_steps),
        save_strategy="steps", save_steps=min(50, max_steps), save_total_limit=2,
        prediction_loss_only=True, report_to=[], push_to_hub=False, dataloader_num_workers=0,
        remove_unused_columns=False, seed=seed, data_seed=seed)
    trainer = CompletionTrainer(model=model, args=arguments, train_dataset=rows["train"],
                      eval_dataset=rows["validation"], data_collator=collate)
    # Loss is a mean over each microbatch's completion tokens; Trainer owns the
    # accumulation scaling. Do not also divide by num_items_in_batch.
    trainer.model_accepts_loss_kwargs = False
    trainer.train()
    evaluation = trainer.evaluate()
    import math
    if not math.isfinite(float(evaluation["eval_loss"])):
        raise Rejected("nonfinite_eval_loss")
    if source_identity() != source:
        raise Rejected("source_changed_during_training")
    model.save_pretrained(str(output / "adapter"), safe_serialization=True)
    tokenizer.save_pretrained(str(output / "adapter"))
    from .common import file_digest
    write_json(output / "run.completed.json", {**record, "status": "complete", "evaluation": evaluation,
              "adapter_files": {path.name: file_digest(path) for path in (output / "adapter").iterdir() if path.is_file()},
              "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
              "packages": {name: importlib.metadata.version(name) for name in hardware["packages"]}})


def merge(*, base: Path, run: Path, output: Path) -> None:
    offline()
    identity = verify_base(base)
    record = loads((run / "run.completed.json").read_text())
    if record["base"] != identity or record["status"] != "complete":
        raise Rejected("adapter_base_identity_mismatch")
    from .common import file_digest
    if any(file_digest(run / "adapter" / name) != sha for name, sha in record["adapter_files"].items()):
        raise Rejected("adapter_file_identity_mismatch")
    import torch
    from peft import PeftModel
    from transformers import Gemma4UnifiedForConditionalGeneration
    model = Gemma4UnifiedForConditionalGeneration.from_pretrained(
        str(base), local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16, device_map={"": "cpu"})
    adapted = PeftModel.from_pretrained(model, str(run / "adapter"), local_files_only=True)
    merged = adapted.merge_and_unload(safe_merge=True)
    private_dir(output)
    merged.save_pretrained(str(output), safe_serialization=True, max_shard_size="4GB")
    import shutil
    for path in base.iterdir():
        if path.is_file() and path.suffix in {".json", ".jinja", ".md", ".txt", ".model"} and path.name not in {
            "config.json", "model.safetensors.index.json"}:
            shutil.copy2(path, output / path.name)
    write_json(output / "chromie-adaptation.json", {"base": identity, "run_sha256": digest(record),
               "files": {path.name: file_digest(path) for path in output.iterdir() if path.is_file()},
               "promotion_allowed": False, "license": "apache-2.0"})
