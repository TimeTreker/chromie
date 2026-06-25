from __future__ import annotations

import unittest

from scripts.deep_thought_response_check import validate_deep_thought_events


def _event(message: str) -> dict[str, str]:
    return {"message": message}


class DeepThoughtResponseCheckTests(unittest.TestCase):
    def test_validate_deep_thought_events_accepts_complete_sequence(self) -> None:
        errors = validate_deep_thought_events(
            [
                _event("router_done: router_ms=1.0 route=deep_thought agents=deepthinking_agent,speaker_agent"),
                _event("deep_thought_ack_schedule: chars=33 text='Okay, let me think about that.'"),
                _event("deep_thought_ack_scheduled: order=0 chunks=1 generation=0"),
                _event("deep_thought_body_cue_launch: skill_id=soridormi.express_attention"),
                _event("interaction_done: agent_ms=12.0 speech=1 skills=0 confirmation=False"),
                _event("skill_result: request_id=cue skill_id=soridormi.express_attention status=completed reason=None message="),
                _event("session_done: scheduled_tts=2 queued_tts=2 played_tts=2 failed_tts=0 skipped_tts=0 response_chars=21 total_ms=30.0"),
            ],
            require_body_cue=True,
            require_body_cue_completed=True,
            require_agent_success=True,
            min_scheduled_tts=2,
        )

        self.assertEqual(errors, [])

    def test_validate_deep_thought_events_reports_missing_human_response(self) -> None:
        errors = validate_deep_thought_events(
            [
                _event("router_done: router_ms=1.0 route=chat agents=speaker_agent"),
                _event("session_done: scheduled_tts=0 queued_tts=0 played_tts=0 failed_tts=0 skipped_tts=0 response_chars=0 total_ms=30.0"),
            ],
            require_body_cue=True,
            require_body_cue_completed=True,
            require_agent_success=True,
            min_scheduled_tts=2,
        )

        self.assertTrue(any("route=deep_thought" in item for item in errors))
        self.assertTrue(any("acknowledgement" in item for item in errors))
        self.assertTrue(any("body cue" in item for item in errors))
        self.assertTrue(any("final response" in item for item in errors))
        self.assertTrue(any("not enough TTS" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
