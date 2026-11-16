"""Optional real-library CPU proof; no downloaded weights or GPU required."""
from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="isolated fine-tuning dependencies are optional")
peft = pytest.importorskip("peft", reason="isolated fine-tuning dependencies are optional")


def test_unified_lora_selected_logits_loss_matches_full_logits_and_backpropagates(tmp_path):
    from transformers import Gemma4UnifiedConfig, Gemma4UnifiedForConditionalGeneration
    from scripts.finetuning.train import attention_targets, completion_loss
    torch.manual_seed(42)
    config = Gemma4UnifiedConfig(text_config={
        "vocab_size": 64, "hidden_size": 64, "intermediate_size": 128,
        "num_hidden_layers": 6, "num_attention_heads": 4, "num_key_value_heads": 2,
        "num_global_key_value_heads": 1, "head_dim": 16, "global_head_dim": 16,
        "layer_types": ["sliding_attention"] * 5 + ["full_attention"],
        "max_position_embeddings": 128, "sliding_window": 16, "attention_k_eq_v": True,
        "num_kv_shared_layers": 0, "use_bidirectional_attention": "vision"},
        vision_config={"mm_embed_dim": 64, "output_proj_dims": 64, "mm_posemb_size": 16,
                       "patch_size": 2, "pooling_kernel_size": 1, "model_patch_size": 2},
        audio_config={"audio_embed_dim": 8, "hidden_size": 8, "audio_samples_per_token": 4, "output_proj_dims": 8})
    base = Gemma4UnifiedForConditionalGeneration(config)
    targets = attention_targets(base)
    assert len(targets) == 23
    model = peft.get_peft_model(base, peft.LoraConfig(task_type=peft.TaskType.CAUSAL_LM,
        r=2, lora_alpha=4, lora_dropout=0, target_modules=targets))
    model.eval()
    ids = torch.tensor([[2, 8, 9, 10, 11, 12, 13, 14]])
    labels = ids.clone()
    labels[:, :5] = -100
    inputs = {"input_ids": ids, "attention_mask": torch.ones_like(ids), "labels": labels}
    full = model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False).logits
    expected = torch.nn.functional.cross_entropy(full[:, :-1].float().reshape(-1, 64), labels[:, 1:].reshape(-1))
    actual, result = completion_loss(model, inputs)
    torch.testing.assert_close(actual, expected, rtol=1e-5, atol=1e-6)
    assert result.logits.shape == (1, 3, 64)
    actual.backward()
    grads = [(name, parameter.grad) for name, parameter in model.named_parameters() if parameter.requires_grad]
    assert grads and all("lora_" in name for name, _ in grads)
    assert any(gradient is not None and gradient.abs().sum() > 0 for _, gradient in grads)
    assert all(gradient is None or torch.isfinite(gradient).all() for _, gradient in grads)
    torch.optim.AdamW((parameter for parameter in model.parameters() if parameter.requires_grad), lr=1e-3).step()
    model.save_pretrained(str(tmp_path / "adapter"), safe_serialization=True)
    assert (tmp_path / "adapter" / "adapter_model.safetensors").is_file()
    with torch.no_grad():
        before = model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False).logits
    merged = model.merge_and_unload(safe_merge=True)
    merged.eval()
    with torch.no_grad():
        after = merged(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False).logits
    torch.testing.assert_close(before, after, rtol=1e-5, atol=1e-6)
