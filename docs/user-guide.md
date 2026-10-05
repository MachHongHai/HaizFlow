# Use HaizFlow

[Home](../README.md) · [Installation](install.md) · [Tiếng Việt](user-guide.vi.md)

## Your first video

1. Choose **New project → Manual**, name it and import a local video.
2. Open **Recognition & translation**, choose recognition and translation models and a target language, then run.
3. Review the captions. Correct recognition errors before generating voice.
4. If needed, use the picture tool to detect and cover original captions and the voice tool to generate speech.
5. Preview the result, check timing and levels, then choose **Export** and a destination.

You do not need to run every tool. Caption-only or audio-only edits can also be exported.

## Choose a workspace

- **Manual:** work on each tool independently and review detailed edits.
- **Automatic:** choose language, models, voice, picture and audio settings before processing a video.
- **Batch:** queue multiple videos with common settings and track each result separately.
- **Downloads:** import videos, channels or audio from supported public links.
- **Social publishing:** prepare posts and publish through your Zernio account.

Back/Forward navigate pages. Undo/Redo in the editor apply to supported edits, not page history.

## Recognition and translation

Choose recognition and translation models and the target language in the recognition tool.

Whisper recognizes speech; HY-MT2 translates locally; Gemini uses an online service with your key. Choose models compatible with the CPU/GPU mode applied in Settings. If a pack or key is missing, read the warning and open Settings to add it; the app does not navigate away from your project automatically.

After vocal separation, check the recognition-source label to see whether it uses the separated voice track or source audio. Review noisy recordings, loud background music and overlapping speech carefully.

## Edit captions

Select a caption on the timeline to adjust text, timing and style. The text-editing dialog lets you navigate between segments. **Save** is enabled only after a change; **Discard changes** restores the saved text.

Adjust font, size, color, outline, shadow and caption area. Drag the caption area in the preview to change its layout. Karaoke follows each word's timing; wrapped lines do not begin highlighting together.

Bangers is bundled. Other fonts must be available on the computer to preserve their appearance in exports. If the app reports a missing or changed font, select a suitable font before exporting.

Review translations and names. If you change wording after generating voice, regenerate the affected segments so speech and captions agree.

## Picture and original captions

In the picture tool, choose whether to preserve the original video or cover its captions. For coverage, choose blur or background patching, review the detected area and apply it.

OCR detects text regions but is not perfect in every frame. Check the coverage at several points. The preview updates after processing so you can review the result without exporting the whole video.

Watermarks may be text, images or video. Only use assets you have permission to use; preview their position, size and opacity.

## Voice

Select a voice before choosing **Generate voice**. Listen to samples before processing the whole video.

- **Built-in voice:** use one voice for the selected speech.
- **Multiple speakers:** group speakers from the source recording and assign consistent voices. This does not automatically clone their original voices.
- **Reference/voice cloning:** use a selected sample you have permission to use. Clear speech from one person with little background music is generally easier to process.

Speaker identification is bundled with the app and runs on CPU. Short turns, overlapping speech and similar voices can be misassigned; review the dialogue, not just its first sentence.

The current OmniVoice checkpoint is **noncommercial**. Do not assume it can be used for ads, monetized videos or client work. You also need appropriate permission for any reference voice.

## Audio and background music

Vocal separation uses Demucs according to the app's CPU/GPU mode. Install its matching pack before running it.

Check the source, voice and music tracks on the timeline. Adjust levels and mute tracks as needed to avoid hearing both original and replacement speech.

Import music from a file or supported link. Its track appears on import. Enable music looping to cover the video, and automatic ducking to lower music under speech. These options are also available in Automatic settings.

## Pause, continue and rerun

**Pause** stops at a point where completed work can be saved. Valid completed results are retained so **Continue** does not need to start everything over.

Do not change settings and continue an old run. The app warns and blocks continuation with a changed configuration. Choose **Rerun** to process using the new settings. Rerunning may replace a tool's current result; review the confirmation.

Video-processing status appears in the app status strip. Resource download/install progress stays on the Resource packs page rather than sharing the video strip.

## Preview and export

Seek using the timeline or preview controls. **Compare** sits with Undo/Redo in the center toolbar, separate from **Export**.

Review the first caption, speaker changes, music sections and the end of the video. Check fonts, caption placement, watermark and audio levels.

Choose **Export**, quality and destination. Existing files require overwrite confirmation. Save exports outside HaizFlow's managed project folders to keep an independent copy. Export does not automatically run additional AI tools you did not select.

## Social publishing

Add and check Zernio keys in **Settings → API Key**. Green/red dots indicate the check result for each key.

Create a publishing project, choose the account and post content, add local videos or renders from projects, and verify the destination before confirming. Use **Open post** after successful publication to check it.

Platforms and Zernio have their own limits, charges and rules. Ensure you have content rights before publishing.

## Manage and troubleshoot

- **Missing pack:** install the matching CPU/GPU pack or use **Check and repair**.
- **Invalid key:** verify the complete key, permissions and account; never include keys in issue reports.
- **No sound:** check that the needed track exists, is not muted and has a nonzero level.
- **Memory error:** close other apps, select a smaller model or disable **Keep models ready**. It reduces repeated loading; it does not increase available memory.
- **Low disk space:** move resources using Settings and keep copies of important media. Do not manually remove active packs or project folders.

See [Installation](install.md) for resources, data and updates. If the problem persists, [report an issue](https://github.com/MachHongHai/HaizFlow/issues) with the version, steps and error screenshot. Hide personal information and keys.
