"""Offline artifact privacy, real resolver replay and adaptation non-regression."""
from __future__ import annotations

import asyncio
import copy
import json
import stat

import pytest

from agent.app.planner import PlannerResolver
from agent.app.social_cognition import SocialCognitionResolver
from scripts.finetuning.common import Rejected, digest, loads, privacy_check, redact
from scripts.finetuning.contracts import receipt_packet, replay
from scripts.finetuning.dataset import export_cases, load_dataset, prepare, receipts, trace_index
from scripts.finetuning.evaluate import compare
from scripts.finetuning.model import tokenize_sample
from shared.chromie_runtime.llm_diagnostics import llm_call_evidence_payload
from tests.test_social_cognition import request as social_request, response as social_response


class RecordingModel:
    def __init__(self, output, *, planner=False):
        self.output = output
        self.receipts = []
        self.planner = planner

    async def generate(self, prompt, **kwargs):
        from agent.app.clients.sglang_protocol import _openai_response_format
        from benchmarks.datasets.fast_planner_daily_life.qualification import declared_ability_needs
        output = copy.deepcopy(self.output.pop(0) if isinstance(self.output, list) else self.output)
        if self.planner:
            output = declared_ability_needs(output, kwargs["response_format"])
        rendered = prompt.render() if hasattr(prompt, "render") else prompt
        messages = [{"role": "system", "content": kwargs["system"]}, {"role": "user", "content": rendered}]
        raw = json.dumps(output, ensure_ascii=False)
        from scripts.finetuning.contracts import DECODING
        decoding = {wire: kwargs["options"][key] for key, wire in DECODING.items() if key in kwargs["options"]}
        self.receipts.append(llm_call_evidence_payload(
            call_id="fixture", purpose="fast_planner" if self.planner else "social_cognition",
            stage=kwargs["prompt_family"], transport="sglang.chat", status="accepted",
            request={"messages": messages, "response_format": _openai_response_format(kwargs["response_format"]), **decoding},
            response={"choices": [{"message": {"role": "assistant", "content": raw}, "finish_reason": "stop"}]},
            parsed_output=output))
        return output

    async def generate_stream(self, prompt, **kwargs):
        raw = await self.generate(prompt, **kwargs)
        self.receipts[-1]["transport"] = "sglang.chat_stream"
        yield json.dumps(raw, ensure_ascii=False)


class Catalog:
    async def prompt_entries(self, **_kwargs):
        return []


def captured_case(role="social_cognition"):
    if role == "social_cognition":
        current, raw = social_request(), social_response()
        model = RecordingModel(raw)
        asyncio.run(SocialCognitionResolver(model, Catalog()).resolve(current))
        variant = "interaction"
    else:
        from tests.planner_test_support import speech_outcomes
        current, raw = speech_outcomes("respond")
        model = RecordingModel(raw, planner=True)
        result = asyncio.run(PlannerResolver(model, Catalog()).resolve(current))
        assert result.disposition == "respond", result.metadata
        variant = "canonical"
    return {"transaction": {"role": role, "variant": variant, "request": current.model_dump(mode="json"),
                            "catalog": {"all": [], "common": [], "index": []}, "settings": {}},
            "calls": [receipt_packet(row) for row in model.receipts]}, model.receipts


def review_for(case, records, **changes):
    review = {"status": "approved", "privacy_approved": True, "semantic_approved": True,
              "reviewer": "offline-human-review", "training_eligible": True, "split": "train",
              "receipt_sha256": [digest(row) for row in records], "sanitized_sha256": digest(case),
              "transaction": case["transaction"], "conversation_group": "conversation-one",
              "contrast_group": "contrast-one", "language": "zh", "category": "progress"}
    review.update(changes)
    return review


@pytest.mark.parametrize("role", ["planner", "social_cognition"])
def test_export_runs_real_current_resolver_and_preserves_exact_json(tmp_path, role):
    packet, records = captured_case(role)
    path = tmp_path / "agent.log"
    # Production logging preserves decoder property order; storage canonicalization
    # is for exported artifacts, never for rewriting a source receipt.
    path.write_text("\n".join("INFO llm_call_evidence " + json.dumps(row, ensure_ascii=True) for row in records))
    sources = receipts([path])
    case = prepare(review_for(packet, records), sources, {}, [], b"x" * 32)
    assert asyncio.run(replay(case))["verdict"] == "pass"
    output = tmp_path / "dataset"
    manifest = export_cases([case], output)
    restored, cases = load_dataset(output)
    assert restored == manifest
    sample = loads((output / "train.jsonl").read_text())
    assert sample["completion"] == packet["calls"][0]["completion"]
    assert "reference_output" not in sample
    assert cases[0]["groups"] != ["conversation-one", "contrast-one"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "train.jsonl").stat().st_mode) == 0o600
    (output / "train.jsonl").write_text("tampered")
    with pytest.raises(Rejected, match="dataset_file_identity"):
        load_dataset(output)


@pytest.mark.parametrize("field,value", [("privacy_approved", False), ("semantic_approved", False),
                                         ("status", "pending_human_review"), ("training_eligible", False),
                                         ("sanitized_sha256", "stale")])
def test_review_and_training_promotion_fail_closed(field, value):
    case, rows = captured_case()
    review = review_for(case, rows, **{field: value})
    with pytest.raises(Rejected):
        prepare(review, {digest(row): row for row in rows}, {}, [], b"x" * 32)


def test_receipts_join_trace_by_identity_and_never_mine_timing_into_answers(tmp_path):
    case, rows = captured_case()
    rows[0]["correlations"]["trace_id"] = "trace-private"
    trace = {"schema_version": 1, "trace_id": "trace-private", "state": "complete", "items": []}
    path = tmp_path / "trace.json"
    path.write_text(json.dumps({"trace": trace}))
    traces = trace_index([path])
    review = review_for(case, rows, trace_sha256=[traces["trace-private"][0]])
    sources = {digest(row): row for row in rows}
    prepared = prepare(review, sources, traces, [], b"x" * 32)
    assert prepared["trace_sha256"] == review["trace_sha256"]
    with pytest.raises(Rejected, match="missing_or_incomplete"):
        prepare(review, sources, {}, [], b"x" * 32)
    with pytest.raises(Rejected, match="no_complete_llm_receipts"):
        receipts([path])


@pytest.mark.parametrize("change", ["failed", "length", "raw_mismatch", "duplicate", "thinking"])
def test_never_train_failed_truncated_or_reasoning_outputs(change):
    _, rows = captured_case()
    row = rows[0]
    if change == "failed":
        row["status"] = "failed"
    elif change == "length":
        row["response"]["provider_response"]["choices"][0]["finish_reason"] = "length"
    elif change == "raw_mismatch":
        row["response"]["raw_model_output"] = "{}"
    elif change == "thinking":
        row["response"]["provider_response"]["choices"][0]["message"]["reasoning_content"] = "private reasoning"
    else:
        raw = '{"disposition":"silence","disposition":"communicate"}'
        row["response"]["raw_model_output"] = raw
        row["response"]["provider_response"]["choices"][0]["message"]["content"] = raw
    with pytest.raises(ValueError):
        receipt_packet(row)


def test_replay_rejects_stale_prompt_and_never_sends_target_to_candidate():
    packet, _ = captured_case()
    class Candidate:
        async def generate(self, prompt, **kwargs):
            assert "completion" not in kwargs and "review" not in kwargs
            assert "reference_output" not in str(prompt)
            return social_response()
    assert asyncio.run(replay(packet, Candidate()))["verdict"] == "pass"
    packet["calls"][0]["messages"][-1]["content"] += "stale prompt"
    with pytest.raises(Rejected, match="current_prompt_or_schema"):
        asyncio.run(replay(packet, Candidate()))


def test_wrong_goal_cannot_be_rescored_into_host_pass():
    packet, _ = captured_case()
    class Candidate:
        async def generate(self, *_args, **_kwargs):
            return social_response(source_goal_ids=["invented-goal"])
    with pytest.raises(ValueError):
        asyncio.run(replay(packet, Candidate()))


def test_streaming_work_only_contract_roundtrips_terminal_frame():
    from tests.test_planner_streaming_commit import _request, _valid_output, _counted
    current = _request()
    model = RecordingModel(_counted(_valid_output()))
    async def capture():
        return [row async for row in PlannerResolver(model, Catalog()).stream_advance(current)]
    assert asyncio.run(capture())[-1].frame_type == "terminal"
    case = {"transaction": {"role": "planner", "variant": "streaming", "request": current.model_dump(mode="json"),
                            "catalog": {"all": [], "common": [], "index": []}, "settings": {}},
            "calls": [receipt_packet(row) for row in model.receipts]}
    assert asyncio.run(replay(case))["result"][-1]["frame_type"] == "terminal"


def test_social_delegation_is_source_only_and_requires_both_ordered_calls():
    current = social_request()
    model = RecordingModel([{"disposition": "deliberate", "activities": [],
                             "reason_summary": "Unresolved source meaning."}, social_response()])
    result = asyncio.run(SocialCognitionResolver(model, Catalog(), deep_model=model).resolve(current))
    assert result.model_call_count == 2
    case = {"transaction": {"role": "social_cognition", "variant": "interaction", "request": current.model_dump(mode="json"),
                            "catalog": {"all": [], "common": [], "index": []}, "settings": {}},
            "calls": [receipt_packet(row) for row in model.receipts]}
    assert asyncio.run(replay(case))["verdict"] == "pass"
    case["calls"].pop()
    with pytest.raises(Rejected, match="unexpected_model_call"):
        asyncio.run(replay(case))


@pytest.mark.parametrize("key", ["groups", "source_receipt_sha256", "messages"])
def test_conversation_contrast_receipt_and_prompt_split_leakage_rejected(tmp_path, key):
    packet, rows = captured_case()
    case = prepare(review_for(packet, rows), {digest(row): row for row in rows}, {}, [], b"x" * 32)
    other = copy.deepcopy(case)
    other.update(id="other", split="frozen_test", groups=["other-group"], source_receipt_sha256=["other-source"])
    if key != "messages":
        other[key] = case[key]
        other["calls"][0]["messages"] = [{"role": "user", "content": "different"}]
    with pytest.raises(Rejected, match="cross_split_leakage"):
        export_cases([case, other], tmp_path / "never-written")
    assert not (tmp_path / "never-written").exists()


def test_redaction_updates_nested_references_and_privacy_backstop_rejects_secrets():
    private = {"user": "mail alice@example.com", "output": {"text": "alice@example.com"}}
    with pytest.raises(Rejected, match="privacy"):
        privacy_check(private)
    safe = redact(private, [{"from": "alice@example.com", "to": "[CONTACT]"}])
    privacy_check(safe)
    assert safe["output"]["text"] == "[CONTACT]"
    with pytest.raises(Rejected, match="redaction_key_collision"):
        redact({"Alice": 1, "Person": 2}, [{"from": "Alice", "to": "Person"}])


def test_redacted_goal_identity_stays_consistent_through_dynamic_schema_and_host():
    from scripts.finetuning.dataset import sanitized_case
    case, records = captured_case()
    sources = {digest(row): row for row in records}
    review = review_for(case, records)
    replacements = [{"from": "goal:1", "to": "goal:anonymous"}]
    sanitized = sanitized_case(review, sources, replacements)
    review["sanitized_sha256"] = digest(sanitized)
    prepared = prepare(review, sources, {}, replacements, b"x" * 32)
    assert "goal:1" not in json.dumps(prepared)
    assert asyncio.run(replay(prepared))["result"]["activities"][0]["source_goal_ids"] == ["goal:anonymous"]


def test_private_review_metadata_cannot_bypass_output_privacy_scan():
    case, rows = captured_case()
    review = review_for(case, rows, category="alice@example.com")
    with pytest.raises(Rejected, match="privacy_scan"):
        prepare(review, {digest(row): row for row in rows}, {}, [], b"x" * 32)


class CharTokenizer:
    def apply_chat_template(self, messages, *, add_generation_prompt, **_kwargs):
        rendered = "".join("<|turn>" + ("model" if row["role"] == "assistant" else row["role"]) + "\n" +
                           row["content"].strip() + "<turn|>\n" for row in messages)
        return rendered + ("<|turn>model\n<|channel>thought\n<channel|>" if add_generation_prompt else "")

    def __call__(self, text, **_kwargs):
        return {"input_ids": list(text.encode())}


def test_completion_mask_and_exact_end_turn_without_prompt_loss_or_truncation():
    sample = {"messages": [{"role": "user", "content": "问候"}], "completion": '{"text":"你好"}'}
    tokenized = tokenize_sample(CharTokenizer(), sample, 1024)
    labels = tokenized["labels"]
    assert bytes(value for value in labels if value != -100).decode() == sample["completion"] + "<turn|>\n"
    assert labels.count(-100) > 0
    with pytest.raises(Rejected, match="oversize_sample_no_truncation"):
        tokenize_sample(CharTokenizer(), sample, 5)
    with pytest.raises(Rejected, match="control_token"):
        tokenize_sample(CharTokenizer(), {**sample, "completion": '"<|turn>"'}, 1024)


def test_attention_adapter_targets_account_for_unified_tied_k_v():
    from types import SimpleNamespace
    from scripts.finetuning.train import attention_targets
    model = SimpleNamespace(config=SimpleNamespace(text_config=SimpleNamespace(
        layer_types=["sliding_attention"] * 5 + ["full_attention"], attention_k_eq_v=True)))
    names = [f"model.language_model.layers.{index}.self_attn.{name}" for index in range(6)
             for name in (["q_proj", "k_proj", "v_proj", "o_proj"] if index < 5 else ["q_proj", "k_proj", "o_proj"])]
    model.named_modules = lambda: [(name, None) for name in names]
    assert len(attention_targets(model)) == 23
    names.append("model.language_model.layers.5.self_attn.v_proj")
    with pytest.raises(Rejected, match="unexpected_gemma4"):
        attention_targets(model)


def reports():
    row = {"case_id": "one", "verdict": "pass", "role": "planner", "variant": "canonical",
           "language": "zh", "category": "confirmation", "elapsed_ms": 1000}
    baseline = {"mode": "native_candidate", "source_unchanged": True, "server_unchanged": True,
                "server_identity": {"quantization": "fp8", "context_length": 65536}, "passed": True, "complete": True,
                "source": {"revision": "frozen"}, "dataset_sha256": "cohort", "split": "frozen_test",
                "expected_cases": ["one"], "results": [row]}
    candidate = copy.deepcopy(baseline)
    review = {"baseline_sha256": digest(baseline), "candidate_sha256": digest(candidate),
              "reviewer": "independent-human", "independent": True,
              "cases": {"one": {"candidate_acceptable": True, "regressed": False}}}
    return baseline, candidate, review


def test_nonregression_requires_native_complete_identical_cohort_and_semantics():
    baseline, candidate, review = reports()
    result = compare(baseline, candidate, review)
    assert result["passed"] and result["promotion_allowed"] is False
    candidate["mode"] = "reference_replay"
    with pytest.raises(Rejected, match="two_complete_native"):
        compare(baseline, candidate, review)


def test_nonregression_rejects_semantic_or_latency_failure_without_averaging():
    baseline, candidate, review = reports()
    review["cases"]["one"]["regressed"] = True
    assert compare(baseline, candidate, review)["passed"] is False
    review["cases"]["one"]["regressed"] = False
    candidate["results"][0]["elapsed_ms"] = 2000
    review["candidate_sha256"] = digest(candidate)
    result = compare(baseline, candidate, review)
    assert result["passed"] is False
    assert result["slices"]["language:zh"]["failures"] == 1


def test_json_duplicates_and_nonfinite_values_are_not_training_data():
    for raw in ('{"a":1,"a":2}', '{"a":NaN}'):
        with pytest.raises(Rejected):
            loads(raw)


def test_candidate_command_preserves_serving_policy_and_requires_explicit_launch(tmp_path):
    from scripts.finetuning.model import LOCK_PATH
    from scripts.finetuning.serve import command
    from scripts.finetuning.common import file_digest
    (tmp_path / "config.json").write_text("{}")
    artifact = {"base": {"lock_sha256": digest(loads(LOCK_PATH.read_text()))},
                "files": {"config.json": file_digest(tmp_path / "config.json")}}
    (tmp_path / "chromie-adaptation.json").write_text(json.dumps(artifact))
    argv = command(merged=tmp_path, image="sha256:" + "a" * 64)
    assert argv[argv.index("--port") + 1] == "30001"
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--model-path") + 1] == "/model"
    assert argv[argv.index("--quantization") + 1] == "fp8"
    assert argv[argv.index("--context-length") + 1] == "65536"
    assert "--enable-priority-scheduling" in argv and "--revision" not in argv
    with pytest.raises(Rejected):
        command(merged=tmp_path, image="latest")
    with pytest.raises(Rejected):
        command(merged=tmp_path, image="sha256:" + "a" * 64, port=30000)
    (tmp_path / "config.json").write_text("corrupt")
    with pytest.raises(Rejected, match="merged_file_identity"):
        command(merged=tmp_path, image="sha256:" + "a" * 64)
