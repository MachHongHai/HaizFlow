# OmniVoice multilingual preset references

The `hoi` Japanese run on 2026-10-31 completed translation but stopped at TTS sentence 10 (`逃げただと？`). Both synthesis attempts failed the waveform tone/DC check. The invalid waveform was not retained, so a false-positive diagnosis was not possible from that run alone.

The integration had a confirmed conditioning gap: `_preset_reference()` accepted only `vi`, `en` and `zh`. Japanese, Korean and Spanish multi-speaker presets therefore ran in instruction-only voice-design mode, without an audio reference. OmniVoice's [official notes](https://github.com/k2-fsa/OmniVoice/blob/master/docs/tips.md) advise providing reference audio for short clips. Its [README](https://github.com/k2-fsa/OmniVoice#python-api) explains that cloning is the more stable mode and voice design is trained on English/Chinese data.

## Current behavior

- Prefer the exact preset's packaged target-language audio and matching transcript.
- For `ja`, `ko` and `es`, if that sample is unavailable, use the **same preset's English sample and its English transcript** for cross-lingual cloning. Never substitute another speaker, source-video dialogue, or an unrelated project's cache.
- Keep target text and the model's target-language parameter unchanged. An English reference is not a request for English output. Cross-lingual cloning can carry an accent from the reference; a verified same-language sample takes precedence when available.
- Missing both samples produces an actionable missing-resource error, not silent instruction-only synthesis.
- Existing prompt reuse keeps reference encoding bounded per preset; there is no additional reference synthesis or ASR validation pass.
- Keep zero fade, normal native duration generation, and the existing tone/DC guard. Invalid output gets one retry with the same identity; a second failure names the exact sentence/language/voice and is never published to the speech cache.
- Update only the OmniVoice Japanese/Korean/Spanish audio cache policy, so old unconditioned parts cannot be mixed with newly conditioned speech. Existing Vietnamese/English/Chinese, Edge and VieNeu cache keys are unaffected by this policy.

The fix addresses the confirmed missing-reference path. It is not a guarantee that a generative TTS model can never emit invalid audio; the waveform guard remains necessary.

## Installed-model validation (2026-10-31)

`scripts/verify-omnivoice-multilingual.py` is an opt-in, offline validation runner. It reads an existing source workspace and writes only a separate evidence directory. It does not modify the source project's state or invoke translation APIs. Run synthesis, render and recognition stages sequentially against the same evidence directory.

On the local RTX 4060 Laptop, using the installed OmniVoice model:

- The original Japanese sentence, exact preset and seed without reference audio failed both attempts. Retained waveforms had approximately 89% DC-dominated active frames, confirming genuine invalid synthesis rather than merely inferring it from the original exception.
- The same sentence with the packaged reference passed on its first attempt.
- All 30 existing Japanese translations from `hoi` synthesized successfully, with one waveform validation per sentence and no retry, in 59.4 seconds (warm model). Peak allocated CUDA memory was approximately 2.35 GiB.
- Six Korean and six Spanish short/long phrases synthesized successfully. This is a sample test, not full coverage of every voice or text.
- The original Japanese video and two generated Korean/Spanish test videos were rendered through the production audio timeline, subtitle and render functions. All three passed full FFmpeg decode and subtitle cue/timeline checks (30/6/6 cues).

Remaining quality caveats:

- Independent Whisper Small and Turbo checks were broadly consistent with Korean/Spanish text, but disagreed on one short Spanish phrase. ASR agreement is not a substitute for listening by a native speaker.
- Japanese full-dialogue ASR detected Japanese, but several readings remained uncertain. Both recognizers transcribed the short `逃げただと？` close to `逃げたらと`; this warrants listening review rather than automatically altering translation or accepting ASR as ground truth.
- That sentence has only a 380 ms source-speech window, so the existing timeline fitter used 4.00x pitch-preserving tempo. Stable native synthesis does not remove this separate intelligibility risk. No timeline or translation policy was changed to hide it.
- Frame inspection confirmed Korean/Spanish glyph rendering. The original project, its cached artifacts and translations were not overwritten.
