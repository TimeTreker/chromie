#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator" / "orchestrator.py"
ENV_COMMON = ROOT / ".env.common"
ENV_LOCAL_EXAMPLE = ROOT / ".env.local.example"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[ok] {label}: already present")
        return text
    if old not in text:
        raise RuntimeError(f"Could not find target for {label}")
    print(f"[patch] {label}")
    return text.replace(old, new, 1)


def patch_orchestrator() -> None:
    if not ORCH.exists():
        raise FileNotFoundError(ORCH)
    text = read(ORCH)

    text = replace_once(
        text,
        "from orchestrator.runtime.session import SessionTracker, now_ms\n",
        "from orchestrator.runtime.session import SessionTracker, now_ms\nfrom orchestrator.runtime.conversation_state import ConversationStateManager\n",
        "import ConversationStateManager",
    )

    text = replace_once(
        text,
        "self.sessions = SessionTracker(enabled=self.enable_session_timing)\n",
        "self.sessions = SessionTracker(enabled=self.enable_session_timing)\n        self.conversation_state = ConversationStateManager.from_env()\n        logger.info(\n            \"Conversation state: enabled=%s conversation_id=%s max_turns=%s idle_s=%s hard_idle_s=%s max_context_chars=%s\",\n            self.conversation_state.enabled,\n            self.conversation_state.conversation_id,\n            self.conversation_state.max_turns,\n            self.conversation_state.soft_idle_timeout_sec,\n            self.conversation_state.hard_idle_timeout_sec,\n            self.conversation_state.max_context_chars,\n        )\n",
        "initialize ConversationStateManager",
    )

    new_build_context = '''    def build_context(self, session_id: str | None) -> dict[str, Any]:
        conversation = self.conversation_state.snapshot()
        return {
            "is_speaking": self.is_playing_audio,
            "current_generation": self.playback_generation,
            "session_id": session_id,
            "conversation_id": conversation.get("conversation_id"),
            "conversation": conversation,
            "history": conversation.get("history", []),
            "pending_tasks": conversation.get("pending_tasks", []),
            "active_pending_tasks": conversation.get("active_pending_tasks", []),
            "robot_state": {
                "available": not self.action_dry_run,
                "source": "host_orchestrator",
            },
        }

'''
    if "conversation = self.conversation_state.snapshot()" not in text:
        pattern = re.compile(
            r"    def build_context\(self, session_id: str \| None\) -> dict\[str, Any\]:\n.*?\n(?=    async def handle_routed_text)",
            re.DOTALL,
        )
        text, n = pattern.subn(new_build_context, text, count=1)
        if n != 1:
            raise RuntimeError("Could not patch build_context block")
        print("[patch] build_context with conversation snapshot")
    else:
        print("[ok] build_context already includes conversation snapshot")

    if "conversation_boundary:" not in text:
        text = replace_once(
            text,
            "    async def handle_routed_text(self, user_text: str, session_id: str) -> None:\n",
            "    async def handle_routed_text(self, user_text: str, session_id: str) -> None:\n        boundary = self.conversation_state.prepare_for_user_text(user_text, session_id)\n        if boundary.get(\"started_new\"):\n            self.session_log(\n                session_id,\n                \"conversation_boundary: started_new=True conversation_id=%s reason=%s\",\n                boundary.get(\"conversation_id\"),\n                boundary.get(\"reason\"),\n            )\n\n",
            "conversation boundary check at turn start",
        )
    else:
        print("[ok] conversation boundary check already present")

    if "context_snapshot: conversation_id=%s history_turns=%s pending_tasks=%s" not in text:
        text = replace_once(
            text,
            "context = self.build_context(session_id)\n        router_start_ms = now_ms()\n",
            "context = self.build_context(session_id)\n        self.session_log(\n            session_id,\n            \"context_snapshot: conversation_id=%s history_turns=%s pending_tasks=%s\",\n            context.get(\"conversation_id\"),\n            len(context.get(\"history\", [])),\n            len(context.get(\"active_pending_tasks\", []) or context.get(\"pending_tasks\", [])),\n        )\n        router_start_ms = now_ms()\n",
            "context snapshot log",
        )
    else:
        print("[ok] context snapshot log already present")

    if "route=\"direct_llm\"" not in text:
        text = replace_once(
            text,
            "        if not self.enable_router:\n            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))\n            return\n",
            "        if not self.enable_router:\n            self.conversation_state.record_user_turn(\n                session_id,\n                user_text,\n                route=\"direct_llm\",\n                intent=\"unknown\",\n                metadata={\"source\": \"router_disabled\"},\n            )\n            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))\n            return\n",
            "record direct-LLM user turn",
        )
    else:
        print("[ok] direct-LLM user turn recording already present")

    user_record = '''        self.conversation_state.record_user_turn(
            session_id,
            user_text,
            route=decision.route,
            intent=decision.intent,
            metadata={"source": decision.source, "confidence": decision.confidence},
        )

'''
    marker = "        if decision.interrupt_current or decision.route == \"interrupt\":\n"
    if user_record.strip() not in text:
        if marker not in text:
            raise RuntimeError("Could not find router decision marker for user turn recording")
        text = text.replace(marker, user_record + marker, 1)
        print("[patch] record routed user turn")
    else:
        print("[ok] routed user turn recording already present")

    # Handle both single-line and already-expanded call shapes.
    old_call = "result = await self.agent_client.run(session, text=user_text, route_decision=decision, sid=session_id, context=context)"
    new_call = "result = await self.agent_client.run(\n                session,\n                text=user_text,\n                route_decision=decision,\n                sid=session_id,\n                context=context,\n                history=context.get(\"history\", []),\n            )"
    if "history=context.get(\"history\", [])" not in text:
        if old_call not in text:
            raise RuntimeError("Could not find AgentClient.run call to add history")
        text = text.replace(old_call, new_call, 1)
        print("[patch] pass history to AgentClient.run")
    else:
        print("[ok] AgentClient.run already receives history")

    if "record_agent_result(session_id, result)" not in text:
        text = replace_once(
            text,
            "            await self.execute_agent_result(result, session_id)\n",
            "            self.conversation_state.record_agent_result(session_id, result)\n            await self.execute_agent_result(result, session_id)\n",
            "record assistant turn from AgentResult",
        )
    else:
        print("[ok] AgentResult recording already present")

    # If router fails, preserve user turn at least as fallback context.
    if "source\": \"router_exception\"" not in text:
        text = replace_once(
            text,
            "            logger.warning(\"Router failed; falling back to direct LLM: %s\", exc)\n            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))\n",
            "            logger.warning(\"Router failed; falling back to direct LLM: %s\", exc)\n            self.conversation_state.record_user_turn(\n                session_id,\n                user_text,\n                route=\"direct_llm\",\n                intent=\"router_exception\",\n                metadata={\"source\": \"router_exception\", \"error\": str(exc)},\n            )\n            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))\n",
            "record router-exception user turn",
        )
    else:
        print("[ok] router-exception user turn recording already present")

    write(ORCH, text)
    print(f"[done] patched {ORCH.relative_to(ROOT)}")


def ensure_env_block(path: Path, block: str, sentinel: str, label: str) -> None:
    if not path.exists():
        path.write_text(block.lstrip(), encoding="utf-8")
        print(f"[patch] created {path.relative_to(ROOT)} with {label}")
        return
    text = read(path)
    if sentinel in text:
        print(f"[ok] {label} already present in {path.relative_to(ROOT)}")
        return
    write(path, text.rstrip() + "\n\n" + block.strip() + "\n")
    print(f"[patch] appended {label} to {path.relative_to(ROOT)}")


def patch_env_files() -> None:
    common_block = """
# Short-term conversation state.
# SID is still one VAD utterance. conversation_id spans multiple turns.
ORCH_ENABLE_CONVERSATION_STATE=1
ORCH_CONVERSATION_ID=local_default
ORCH_CONVERSATION_MAX_TURNS=12
ORCH_CONVERSATION_IDLE_TIMEOUT_SEC=180
ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC=900
ORCH_CONVERSATION_TURN_MAX_TEXT_CHARS=260
ORCH_CONVERSATION_MAX_CONTEXT_CHARS=2200
ORCH_CONVERSATION_MAX_PENDING_TASKS=8
# Optional phrase overrides use | as separator.
# ORCH_CONVERSATION_RESET_PHRASES=new topic|start over|换个话题|重新开始
# ORCH_CONVERSATION_FOLLOWUP_PHRASES=when|answer|result|what about|刚才|结果|什么时候
"""
    ensure_env_block(ENV_COMMON, common_block, "ORCH_ENABLE_CONVERSATION_STATE", "conversation state env")

    local_block = """
# Conversation state overrides.
# ORCH_ENABLE_CONVERSATION_STATE=1
# ORCH_CONVERSATION_IDLE_TIMEOUT_SEC=180
# ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC=900
# ORCH_CONVERSATION_MAX_TURNS=12
# ORCH_CONVERSATION_MAX_CONTEXT_CHARS=2200
# ORCH_CONVERSATION_RESET_PHRASES=new topic|start over|换个话题|重新开始
"""
    ensure_env_block(ENV_LOCAL_EXAMPLE, local_block, "ORCH_CONVERSATION_IDLE_TIMEOUT_SEC", "conversation state local example")


def main() -> int:
    try:
        patch_orchestrator()
        patch_env_files()
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    print("[done] conversation context patch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
