# HaizFlow user guide

[Documentation](README.md) · [Repository](../README.md) · [Tiếng Việt](user-guide.vi.md)

This guide explains the application in task order. It assumes no knowledge of the internal models or media pipeline.

## 1. Before you begin

HaizFlow is a Windows desktop application. It stores projects locally and can perform the core recognition, translation, local speech, audio, and video operations without a paid inference API.

Prepare the following:

- a readable source video with an audio track;
- enough free storage for the source, generated assets, caches, and export;
- an Internet connection for first-use model downloads and any online feature;
- optional NVIDIA GPU resources for faster local inference.

Local processing does not mean every feature is offline. Edge TTS, URL imports, model installation, and social publishing require a network connection.

## 2. Install and open HaizFlow

For a source checkout:

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow
powershell -ExecutionPolicy Bypass -File .\scripts\install-desktop-env.ps1
.\.venv\Scripts\python.exe .\haizflow_desktop.py
```

The first setup can take time because Torch, Qt, and media libraries are large. Do not interrupt PowerShell while dependencies are being synchronized.

When a model is first required, HaizFlow shows its download or preparation state in the bottom activity strip. A model becomes available only after its expected size and SHA-256 checksum are verified.

## 3. Understand the application shell

The persistent top bar contains navigation, Projects, Edit, Settings, and Help. Back and Forward follow route history. Undo and Redo belong to Edit history and are independent from navigation.

The main navigation contains:

- **Home:** recent projects, primary actions, developer links, and the tutorial placeholder.
- **Projects:** all project types in a filterable grid.
- **Downloads:** projects for video, channel, and audio acquisition.
- **Social publishing:** publishing projects and their queues.
- **Settings:** language, processing device, runtime information, model storage, privacy, and Manual cache cleanup.

When a project opens, the side navigation is hidden so the preview and editing surface receive more room. Use Home or Projects in the top bar to leave the workspace.

## 4. Choose a project type

Select **New project**, then choose the mode that matches the job.

### Automatic

Use Automatic when one configuration should produce a complete localized video with minimal intervention. The pipeline is ordered and supports pause, resume, and recovery from validated checkpoints.

### Manual

Use Manual when you need independent control. Recognition and translation, subtitle editing, image cleanup, voice generation, audio mixing, and export are tools rather than mandatory steps.

### Batch

Use Batch for several videos with a common baseline. Each video retains its own status and output. A per-video override does not silently replace the batch baseline for new imports.

### Download

Use Download to save public video, channel, or audio sources into a managed project. Supported services can change their public access behavior; authentication may be required by the source platform.

### Social publishing

Use Social publishing to prepare captions and queue exported videos through a Zernio account that you configure.

## 5. Import media

### From a local file

1. Select **From file**.
2. Choose a supported video.
3. Wait for integrity validation and thumbnail generation.
4. Confirm that the preview and duration are available before processing.

HaizFlow copies or registers the media within the project workflow. Do not remove the project folder while the application is running.

### From a public link

1. Select **From link**.
2. Paste a direct public video URL. Share text containing one supported URL is also accepted.
3. Select **Check** and review title, platform, creator, duration, and thumbnail.
4. Select **Download and import**.

Metadata and download operations use bounded retries for temporary DNS, timeout, HTTP, and expired-manifest failures. A private, removed, region-locked, or login-protected video is reported directly instead of being retried indefinitely.

If a link fails:

1. Open the URL in a normal browser and confirm that it is public.
2. Check the platform authentication setting when applicable.
3. Retry after a short delay if the platform is rate-limiting requests.
4. Update the checkout if the platform changed its page format and yt-dlp released a fix.

## 6. Run an Automatic project

1. Add the source video.
2. Choose the recognition model and target language.
3. Choose OmniVoice for local speech or Edge TTS for an online voice.
4. Configure original-subtitle treatment:
   - keep the original picture;
   - blur the detected subtitle region;
   - patch the detected region.
5. Choose original audio or voice separation.
6. Add optional background music and watermark.
7. Set source, speech, and music levels.
8. Start processing.

The command bar reports the active operation. Pausing preserves completed checkpoints. Restarting may invalidate downstream artifacts, so use it only when a clean run is required.

After translation, use the subtitle editor to correct text or timing. HaizFlow does not add or delete subtitle segments in this editor. Text changes invalidate speech for the affected sentence; timing changes reposition existing speech without synthesizing it again.

## 7. Work in the Manual editor

Manual tools are independent. You can select any available tool and return to a cached variant later.

### Source

- Replace the source from a file or link.
- Select **Keep original audio** to use the source track.
- Select **Separate vocals**, then run separation to create vocals and background variants with Demucs.

Changing the active source-audio mode uses a matching cached variant when available. It does not run recognition automatically.

### Recognition & translation

Choose the recognition model and target language, then run the command. The result is a subtitle document with timing; it does not create speech.

Running this tool again replaces the translated subtitle document. Existing subtitle style, position, image configuration, watermark, music, and levels remain project settings. Existing speech is invalidated because it no longer represents the new text.

### Subtitles

- Click a subtitle clip on the timeline or click the subtitle in the result preview.
- Edit the complete segment text in the inspector.
- Drag the subtitle on the result preview to change the project position.
- Drag the transform handle to change the project subtitle size.
- Drag clip edges on the timeline to change timing.

Text saves automatically. The status changes from **Saving** to **Saved**. Clicking an empty preview area commits the draft, removes keyboard focus, and hides the transform frame.

Undo and Redo operate on editor history, including text, timing, visual, audio, voice, and project settings. They are not the same as Back and Forward navigation.

### Image

Choose whether to keep or conceal the source subtitles. When concealment is selected, choose blur or patch before the operation starts. The detected OCR region is a visual layer below the translated subtitle layer.

Watermark changes belong here. Subtitle content, size, and timing do not.

### Voice

Select **Generate voice** to open the voice dialog. Choose the provider, voice, and scope, then confirm; closing the dialog leaves the current voice and cache untouched. After speech exists, **Change voice** and **Regenerate** open the same dialog instead of changing the project immediately.

Use **Entire video** for one consistent voice, or **This segment** to synthesize only the subtitle selected on the timeline. Segment-level changes reuse every unaffected clip. Only missing or invalidated sentence clips are synthesized.

- OmniVoice runs locally after its assets are installed.
- Edge TTS sends subtitle text to the selected online service.
- Multi-speaker recognition is shown only when the selected provider supports that workflow.

Editing one sentence after speech exists schedules that sentence for refresh; unchanged sentences retain their valid clips. Changing timing alone does not call TTS.

### Audio

Source/background, speech, and music levels are applied to preview directly. Add background music from a file or supported link. Audio settings do not run recognition, translation, separation, or TTS.

If a required voice clip is missing, the interface identifies the missing data rather than generating it silently.

### Export

Export uses the current state. OCR cleanup, synthesized voice, music, watermark, or translated subtitles may be omitted if you did not enable or create them. The export command does not run missing AI tools on your behalf.

When export completes, use the visible output action to play the video or open its containing folder.

## 8. Preview, timeline, and playback

- The source preview and result preview have independent play, pause, stop, mute, and fullscreen controls.
- **Play both** starts synchronized comparison playback.
- Drag the transport slider or timeline playhead to seek. The UI follows the pointer immediately and sends consolidated seek requests to the player.
- Preview generation keeps the last valid frame visible while a replacement is prepared.
- A thin progress indicator appears only when the selected tool is producing a replacement artifact.

The preview uses lower-cost proxies and cached layers for responsiveness. The final export still uses the configured output rendering path.

## 9. Batch processing

1. Create a Batch project.
2. Add files or import supported links.
3. Set the shared processing configuration.
4. Review any per-video override.
5. Start the queue.

Each row shows its own state and progress. Failed videos can be retried without discarding successful videos. Changing the batch baseline affects the intended batch configuration; a temporary per-video view does not become the new baseline automatically.

## 10. Downloads

The Downloads workspace has three tabs:

- **Video:** inspect one URL, review metadata, then download.
- **Channel:** inspect a public channel/profile, select candidates, then queue downloads.
- **Audio:** download audio from a supported URL or extract audio from a local media file.

Downloads continue through the project queue. Temporary files are staged in project-owned directories and are promoted only after validation.

## 11. Social publishing

1. Create or open a Social publishing project.
2. Connect Zernio and store the API key through the application.
3. Set default caption and post options.
4. Add media from a file, folder, or another HaizFlow project.
5. Review the platform, content, and queue state.
6. Confirm publishing.

Publishing uploads media to a third-party service and is not a local-only operation. Review Zernio and destination-platform terms, quota, privacy, and pricing before use. Published items expose **Open post**; invalid actions are not offered.

## 12. Storage and cache

Projects contain source references or managed copies, metadata, logs, previews, caches, and exports. Manual caches are content-addressed so a previous valid voice, OCR, visual, or audio variant can be reactivated.

Use **Settings → Clear temporary Manual data** when cache storage must be reclaimed. Active inputs and exports are not cache entries and must not be deleted by this action. Close active work before manually moving a project directory.

Advanced source users can set `HAIZFLOW_HOME` in `.env` to contain models, cache, data, and temporary files under a chosen local directory.

## 13. Troubleshooting

### The application is preparing a model

Wait for the bottom activity strip to complete. Model initialization and actual job progress are separate states. If preparation fails, open the technical log and verify storage, network, checksum, and GPU memory.

### A URL fails on the first attempt

Current builds automatically retry known temporary failures with a fresh yt-dlp session. If the final error says private, unavailable, unauthorized, or login required, retrying without changing access conditions will not help.

### Preview is silent

Confirm that the expected source/voice/music track exists, is not muted, and has non-zero volume. In Manual projects, generating voice and selecting/mixing audio are independent actions.

### Preview differs briefly after opening a project

Wait for the active cached preview to finish loading. The result pane should keep the last valid frame and swap only to a complete replacement. If it remains incorrect, open the technical log and report the project state without attaching private media.

### Vietnamese input loses the final word

Current builds commit Windows IME composition before focus changes and save actions. If the issue persists, include the Windows version, input method, affected field, and exact reproduction text in an issue.

### The application becomes slow

- Stop unnecessary active jobs.
- Confirm that the configured processing device has available memory.
- Clear inactive Manual cache variants if disk pressure is high.
- Avoid placing active projects on a slow network filesystem.

## 14. Report a problem

Open [GitHub Issues](https://github.com/MachHongHai/HaizFlow/issues) and include:

- the action you performed;
- expected and actual behavior;
- a minimal reproducible source when sharing is permitted;
- the visible error and relevant technical log excerpt;
- Windows, GPU, and application version information.

Do not publish credentials, private links, full project metadata, or copyrighted media without permission.
