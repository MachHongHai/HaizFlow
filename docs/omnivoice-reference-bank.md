# OmniVoice synthesis references

Runtime synthesis now prefers the short, lossless reference bank under
`src/haizflow/desktop/assets/voice_samples/references/omnivoice/manifest.json`.
This is separate from the UI preview MP3 catalog; preview playback stays cheap.

The first bank contains the approved `omnivoice:male` and `omnivoice:female`
presets in Vietnamese, English, Chinese, Japanese, Korean and Spanish (12 WAVs).
Each is mono PCM16 at 24 kHz, 3–10 seconds, with its own matching transcript and
SHA-256. These are synthetic references preserving the existing preset identity,
not new recordings by native speakers. Other presets retain their own original
reference; a missing/corrupt asset must never silently substitute another voice.

GPU synthesis defaults to 48 steps, CPU to 32; fade is zero. Existing lightweight
waveform safeguards and bounded gain matching to VieNeu remain enabled. There
is no ASR-based retry, reference generation or transcoding added to normal video
processing. Reference prompts remain bounded and reused while the model is warm;
their cache keys include the reference file identity and transcript.

The bank was verified with local Whisper large-v3-turbo without an initial prompt.
ASR is an intelligibility check, not a naturalness/accent score. Earlier Whisper
Small mismatches on short Vietnamese/Korean examples did not reproduce in the
stronger recognizer; do not add production retries merely to satisfy Small.

To rebuild a candidate bank (not during user processing):

```powershell
python scripts/prepare-omnivoice-references.py --stage synthesize --models D:/HaizFlowData/models --voices omnivoice:male,omnivoice:female
python scripts/prepare-omnivoice-references.py --stage verify --models D:/HaizFlowData/models --voices omnivoice:male,omnivoice:female --asr-model large-v3-turbo --asr-device cuda --publish
```

Synthesis and verification run in separate processes so TTS and ASR models do
not overlap. Test held-out phrases with `scripts/audition-omnivoice-references.py`
and listen before promoting a new bank. Update the OmniVoice audio policy version
in `tts_quality.py` when promoting changed references so Manual/Auto/Batch do not
reuse old synthesis results. This does not invalidate Edge or VieNeu caches.

The setuptools data patterns and the existing desktop asset-tree packaging both
include the bank. No separate model download is needed for these small WAVs.
