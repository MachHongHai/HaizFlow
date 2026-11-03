# Synthetic OmniVoice regression audio

`omnivoice-ja-voiced-prefix-2.wav` and `omnivoice-ja-voiced-prefix-3.wav` are
one-second PCM16 excerpts generated locally with k2-fsa/OmniVoice (48 steps,
packaged `omnivoice:male` Japanese reference, zero fade). They contain connected
speech, not a recording of an external speaker or a user's source video.

They reproduce a false repeated-beep alarm: 40 ms vowel frames have dominant
ridges near 425–475 Hz, separated by lower-energy consonants rather than silence.
The original complete utterances were independently transcribed correctly by
Whisper large-v3-turbo, without an initial prompt:

```text
これは競技用の唐辛子だからね。
```

These fixtures test the acoustic classifier, not pronunciation or naturalness.
