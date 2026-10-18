from __future__ import annotations

import unittest

from tts.text_normalization import has_speakable_content, strip_speech_markup


class SpeechTextNormalizationTests(unittest.TestCase):
    def test_markup_is_removed_and_whitespace_collapsed(self) -> None:
        self.assertEqual(strip_speech_markup("  **Hi** `there`\n# [ok] "), "Hi there ok")
        self.assertEqual(strip_speech_markup(None), "")

    def test_speakable_content_rule(self) -> None:
        self.assertTrue(has_speakable_content("你好", min_chars=2))
        self.assertFalse(has_speakable_content("3.", min_chars=1))
        self.assertFalse(has_speakable_content("!!", min_chars=1))
        self.assertFalse(has_speakable_content("a", min_chars=2))


if __name__ == "__main__":
    unittest.main()
