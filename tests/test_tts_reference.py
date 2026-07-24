from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))

from scripts.promote_builtin_tts_voices import promote
from scripts.tts_reference import install_reference, validate_reference_dir
from voice_catalog import resolve_voice_profile, validate_voice_catalog


def wav_fixture(path: Path, *, payload: bytes = b"\x00\x00" * 32) -> None:
    data_size = len(payload)
    riff_size = 36 + data_size
    header = (
        b"RIFF"
        + riff_size.to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + data_size.to_bytes(4, "little")
    )
    path.write_bytes(header + payload)


class TtsReferenceTests(unittest.TestCase):
    def test_install_and_validate_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "voice.wav"
            output = root / "installed"
            wav_fixture(source)
            result = install_reference(
                source_wav=source,
                transcript=" 你好， 我是 Chromie。 ",
                license_id="owner-authorized",
                output_dir=output,
            )
            self.assertEqual(result["text"], "你好， 我是 Chromie。")
            self.assertEqual(result["license_id"], "owner-authorized")
            self.assertTrue((output / "reference.wav").is_file())
            self.assertEqual(validate_reference_dir(output)["audio_sha256"], result["audio_sha256"])

    def test_validation_rejects_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wav_fixture(root / "reference.wav")
            (root / "reference.json").write_text(
                json.dumps(
                    {
                        "text": "你好",
                        "license_id": "owner-authorized",
                        "audio_sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "does not match"):
                validate_reference_dir(root)

    def test_install_requires_transcript_and_license(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "voice.wav"
            wav_fixture(source)
            with self.assertRaisesRegex(ValueError, "transcript"):
                install_reference(
                    source_wav=source,
                    transcript="",
                    license_id="owner-authorized",
                    output_dir=root / "out-a",
                )
            with self.assertRaisesRegex(ValueError, "license"):
                install_reference(
                    source_wav=source,
                    transcript="你好",
                    license_id="",
                    output_dir=root / "out-b",
                )


class BuiltinVoiceCatalogTests(unittest.TestCase):
    def test_promote_creates_three_valid_git_controlled_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "private"
            output = root / "assets"
            source.mkdir()
            wav_fixture(source / "chromie_zh.wav", payload=b"\x01\x00" * 64)
            wav_fixture(source / "chromie_en.wav", payload=b"\x02\x00" * 64)
            wav_fixture(source / "chromie_mixed.wav", payload=b"\x03\x00" * 64)
            (source / "chromie_zh.txt").write_text("你好，我是 Chromie。", encoding="utf-8")
            (source / "chromie_en.txt").write_text("Hello, I am Chromie.", encoding="utf-8")
            (source / "chromie_mixed.txt").write_text("你好，I am Chromie.", encoding="utf-8")

            result = promote(source_dir=source, output_dir=output, transcripts={})
            self.assertEqual(result["default_speaker_id"], "chromie_mixed")
            self.assertEqual(
                result["speaker_ids"],
                ["chromie_en", "chromie_mixed", "chromie_zh"],
            )
            catalog = validate_voice_catalog(output)
            self.assertEqual(
                resolve_voice_profile(
                    catalog,
                    requested_speaker_id="default",
                    language_hint="zh-CN",
                    text="你好",
                ).speaker_id,
                "chromie_zh",
            )
            self.assertEqual(
                resolve_voice_profile(
                    catalog,
                    requested_speaker_id="default",
                    language_hint="en-US",
                    text="Hello",
                ).speaker_id,
                "chromie_en",
            )
            self.assertEqual(
                resolve_voice_profile(
                    catalog,
                    requested_speaker_id="default",
                    language_hint=None,
                    text="你好 Chromie",
                ).speaker_id,
                "chromie_mixed",
            )

    def test_promote_accepts_chromie_cn_source_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "private"
            output = root / "assets"
            source.mkdir()
            wav_fixture(source / "chromie_cn.wav")
            wav_fixture(source / "chromie_en.wav")
            wav_fixture(source / "chromie_mixed.wav")
            result = promote(
                source_dir=source,
                output_dir=output,
                transcripts={
                    "chromie_zh": "你好",
                    "chromie_en": "Hello",
                    "chromie_mixed": "你好 Hello",
                },
            )
            self.assertTrue(result["catalog_revision"])
            self.assertTrue((output / "chromie_zh" / "reference.wav").is_file())

    def test_promote_requires_exact_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "private"
            source.mkdir()
            for name in ("chromie_zh.wav", "chromie_en.wav", "chromie_mixed.wav"):
                wav_fixture(source / name)
            with self.assertRaisesRegex(ValueError, "exact transcript"):
                promote(source_dir=source, output_dir=root / "assets", transcripts={})
