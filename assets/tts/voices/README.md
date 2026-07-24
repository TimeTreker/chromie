# Built-in Chromie voices

This directory is the source-controlled CosyVoice voice catalog. The intended
profiles are `chromie_zh`, `chromie_en`, and `chromie_mixed`; the mixed profile
is the logical default, while `speaker_id=default` routes Chinese and English
requests to their language-specific profiles.

The binary WAVs are intentionally promoted from the project owner's existing
AI-generated local assets rather than synthesized or substituted by the build.
Run:

```bash
python scripts/promote_builtin_tts_voices.py \
  --source-dir .chromie/private/tts-voice
```

The command discovers exact transcript sidecars where available. If a sidecar
is absent, pass `--zh-transcript`, `--en-transcript`, or `--mixed-transcript`.
After promotion, commit `assets/tts/voices/manifest.json` and all three profile
directories. A clean clone will then start without `.chromie` voice state.
