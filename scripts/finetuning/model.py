"""Local-only identity and hardware preflight; no implicit model downloads."""
from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
from typing import Any

from .common import Rejected, digest, file_digest, loads

LOCK_PATH = Path(__file__).with_name("model.lock.json")


def offline() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["WANDB_DISABLED"] = "true"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.umask(0o077)


def verify_base(base: Path, *, weights: bool = True) -> dict[str, Any]:
    lock = loads(LOCK_PATH.read_text())
    if not base.is_dir():
        raise Rejected("local_hf_snapshot_required")
    for name, sha in lock["files"].items():
        if name == "model.safetensors" and not weights:
            continue
        if not (base / name).is_file() or file_digest(base / name) != sha:
            raise Rejected("pinned_base_file_mismatch:" + name)
    config = loads((base / "config.json").read_text())
    text = config["text_config"]
    if (config["architectures"] != [lock["architecture"]] or config["model_type"] != lock["model_type"]
            or text["num_hidden_layers"] != 48 or text["hidden_size"] != 3840
            or text["enable_moe_block"] is not False or text["num_kv_shared_layers"] != 0):
        raise Rejected("gemma4_unified_dense_contract_mismatch")
    return {"model_id": lock["model_id"], "revision": lock["revision"],
            "lock_sha256": digest(lock), "weights_verified": weights}


def gpu_preflight() -> dict[str, Any]:
    import torch
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise Rejected("one_visible_cuda_gpu_required")
    major, minor = torch.cuda.get_device_capability(0)
    if (major, minor) != (12, 0) or not torch.cuda.is_bf16_supported():
        raise Rejected("blackwell_sm120_bf16_required")
    total = torch.cuda.get_device_properties(0).total_memory
    free, _ = torch.cuda.mem_get_info(0)
    if total < 30 * 1024**3 or free < 27 * 1024**3:
        raise Rejected("release_serving_asr_tts_gpu_memory_before_training")
    # Actually execute on this GPU: wheel metadata alone cannot prove sm120 works.
    a = torch.randn((64, 64), device="cuda", dtype=torch.bfloat16)
    if not torch.isfinite(a @ a).all().item():
        raise Rejected("cuda_bf16_probe_failed")
    import bitsandbytes as bnb
    layer = bnb.nn.Linear4bit(64, 64, quant_type="nf4", compute_dtype=torch.bfloat16).cuda()
    x = torch.randn((2, 64), device="cuda", dtype=torch.bfloat16, requires_grad=True)
    loss = layer(x).float().square().mean()
    loss.backward()
    if x.grad is None or not torch.isfinite(x.grad).all().item():
        raise Rejected("bitsandbytes_nf4_backward_probe_failed")
    return {"gpu": torch.cuda.get_device_name(0), "compute_capability": [major, minor],
            "total_bytes": total, "free_bytes": free, "cuda": torch.version.cuda,
            "packages": {name: importlib.metadata.version(name)
                         for name in ("torch", "transformers", "peft", "accelerate", "bitsandbytes")}}


def tokenize_sample(tokenizer: Any, sample: dict[str, Any], max_length: int) -> dict[str, Any]:
    messages = sample["messages"]
    # Use the pinned official template, including its empty thought channel. Train
    # JSON content + end-of-turn only, never user/system text or a hidden rationale.
    prefix = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                            enable_thinking=False)
    completion = sample["completion"].strip()
    if "<|" in completion or "<turn|>" in completion:
        raise Rejected("control_token_in_completion")
    plain = tokenizer.apply_chat_template([*messages, {"role": "assistant", "content": completion}],
                                         tokenize=False, add_generation_prompt=False, enable_thinking=False)
    # At this pinned revision, completed assistant messages omit the empty thought
    # channel that add_generation_prompt emits. Align SFT to non-thinking inference
    # explicitly, verifying both official renderings before adding that prefix.
    empty_thought = "<|channel>thought\n<channel|>"
    if not prefix.endswith(empty_thought):
        raise Rejected("nonthinking_generation_prefix_changed")
    if plain != prefix[:-len(empty_thought)] + completion + "<turn|>\n":
        raise Rejected("official_assistant_template_changed")
    full = prefix + completion + "<turn|>\n"
    prefix_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
    ids = tokenizer(full, add_special_tokens=False)["input_ids"]
    if ids[:len(prefix_ids)] != prefix_ids or len(ids) <= len(prefix_ids):
        raise Rejected("chat_template_completion_boundary_mismatch")
    if len(ids) > max_length:
        raise Rejected("oversize_sample_no_truncation")
    return {"input_ids": ids, "attention_mask": [1] * len(ids),
            "labels": [-100] * len(prefix_ids) + ids[len(prefix_ids):]}
