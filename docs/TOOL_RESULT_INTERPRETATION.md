# Tool Result Interpretation

## Purpose

Tool and provider output is evidence, not user-facing response text. Chromie keeps
the complete schema-validated result for reconciliation, follow-up questions,
observability, and incident evidence, but speaks only the information needed to
answer the current user request.

The maintained flow is:

```text
user request
  -> semantic tool selection and execution
  -> closed provider output schema
  -> bounded ModelObservation
  -> tool-result interpretation
  -> trusted grounding and speech-budget validation
  -> one concise spoken answer
```

This boundary applies to the built-in weather lookup and to any canonical Skill
Runtime result that exposes a schema-validated `ModelObservation`.

## Semantic ownership

The model owns:

- deciding whether the request calls for a direct answer, a normal summary, or a
  detailed answer;
- selecting the evidence fields relevant to the user's actual question;
- drawing a natural-language conclusion from those selected facts;
- phrasing the final spoken response in the user's language.

The Host and Agent contract boundary owns:

- retaining the complete tool result unchanged;
- exposing only closed, schema-validated, bounded observations;
- requiring every selected fact to reference one exact evidence ID and RFC 6901
  JSON Pointer;
- rejecting unknown, duplicate, collection-valued, or stale fact references;
- rejecting unsupported numeric claims, internal IDs, raw JSON/payload narration,
  and speech outside the selected sentence and character budgets;
- falling back to a trusted adapter-owned compact response, or the conservative
  post-execution response, when interpretation is unavailable.

No user-text phrase table chooses which fields matter. Relevance selection is a
model responsibility constrained by exact evidence references.

## Contract

`shared/chromie_contracts/tool_result.py` defines:

- `ToolResultEvidence`: one complete bounded tool observation plus status and
  digest;
- `ToolResultFactReference`: an exact evidence ID and JSON Pointer;
- `ToolResultInterpretationRequest`: the original user need, language, complete
  evidence set, and spoken budgets;
- `ToolResultInterpretation`: the concise answer, answer mode, selected facts,
  confidence, and bounded metadata.

The Agent endpoint is:

```text
POST /tool-result/interpret
```

The endpoint is available when `AGENT_TOOL_RESULT_INTERPRETER_ENABLED=1`.
Normal defaults use the same quality model family as Response Composer, but the
stage has its own timeout and context/output budgets.

## Weather example

A weather provider may return condition, current temperature, apparent
temperature, daily high and low, precipitation, wind, date, and units. For:

```text
今天重庆天热不热？
```

an acceptable response is:

```text
很热，现在37℃，体感42℃。
```

The full report remains attached to the Agent result and can support a later
question such as whether it will rain. It is not read field by field merely
because the provider returned it.

## Failure behavior

- Invalid model output with a valid trusted compact fallback uses that fallback.
- Invalid model output without a fallback returns `unavailable`; the Host uses
  its conservative evidence-bound outcome response.
- Missing or invalid provider output never enters this stage as available data.
- A model answer containing a number absent from the original question and all
  selected scalar evidence is rejected.
