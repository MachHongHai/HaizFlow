# HaizFlow user guide

[Documentation](README.md) · [Repository](../README.md) · [Tiếng Việt](user-guide.vi.md)

This guide covers installation, projects, editing and routine troubleshooting. You do not need to know which internal model or file format HaizFlow uses.

## 1. Before installation

HaizFlow supports Windows 10 version 1809 or later and Windows 11 on x64 computers. The official minimum is 16 GiB RAM. An NVIDIA GPU is optional; it shortens processing time for compatible models but is not required for the Core application.

Allow space for four separate items:

1. the Core application;
2. the engines and models you choose in Resource packs;
3. source videos and exports;
4. temporary editing data.

Setup displays the measured requirement for its exact build. The current verified Core artifact is 477 MiB and Setup recommends 4 GiB of free space. Optional resource packs and project media are measured separately and are not included in the Core figure.

HaizFlow can perform recognition, translation, local speech, audio separation and OCR on the computer after the appropriate packs are installed. Edge TTS, public-link imports, resource downloads and social publishing require an Internet connection.

## 2. Install and open

For a published build, start Setup and use the location suggested by Windows unless you have a reason to choose another local drive. Do not place engines or models on a network drive.

To run from source:

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow
powershell -ExecutionPolicy Bypass -File .\scripts\install-desktop-env.ps1
.\.venv\Scripts\python.exe .\haizflow_desktop.py
```

The Home page opens without waiting for an AI model. If **Keep models ready** is enabled, HaizFlow prepares installed models in a separate process once the interface is responsive. This preparation does not start work on a video.

## 3. Install resource packs

Open **Settings → Resource packs**. Packs are grouped by processor, recognition, translation, voice and picture.

Each row shows download size, installed size, version, location and current state. Before installation, HaizFlow also counts extraction space, the previous version retained for rollback and 2 GiB of free-space reserve.

- **Install** downloads and verifies a pack.
- **Pause** and **Resume** control a download without discarding valid partial data.
- **Repair** checks and replaces damaged files.
- **Remove** deletes a pack that no worker is using.
- **Move storage** transfers all managed resources to another local drive, verifies the copy and only then removes the old copy.

HaizFlow does not download a missing pack automatically. If a tool needs one, the message names the missing packs and opens the correct section in Settings. Return to the project and run the command after installation.

## 4. Navigate the application

The top bar contains Home, Back, Forward, Projects, Edit, Settings and Help.

- **Back** and **Forward** move through pages you have visited.
- **Undo** and **Redo**, under Edit, reverse supported edits. They do not act as page navigation.
- **Help** opens the About window and support links.

The side navigation is visible on Home, Projects, Downloads and Social publishing. It is hidden inside a project to leave more space for the video and timeline. Use Home or Projects in the top bar to leave a project.

## 5. Create a project

Select **New project**, then choose the type that matches the work.

- **Automatic:** one video, one set of options and an ordered processing job. It supports pause, resume and validated recovery.
- **Manual:** independent tools for source, translation, subtitles, picture, voice, sound and export.
- **Batch:** several videos with a shared base configuration and a separate result for each video.
- **Download:** video, channel or audio acquisition from a supported public source.
- **Social publishing:** preparation and submission through a Zernio account supplied by the user.

Home lists recent projects. The Projects page keeps the full collection in a searchable, filterable card grid.

## 6. Import a video

### From a file

1. Select **From file**.
2. Choose a supported video.
3. Wait until the thumbnail and duration appear.
4. Check that the video can be played before starting a long operation.

Do not rename, move or delete files inside an open project directory.

### From a public link

1. Select **From link**.
2. Paste a public video URL. Text containing one supported URL is accepted as well.
3. Select **Check**.
4. Review the title, platform, creator, duration and thumbnail.
5. Select **Download and import**.

HaizFlow retries temporary DNS, timeout, HTTP and expired-media errors with a fresh yt-dlp session. It does not endlessly retry a private, removed, region-restricted or login-protected video.

If inspection fails, open the URL in a browser first. Confirm that the content is public, update platform authentication if the service requires it, and try again after a short wait if the service is limiting requests.

## 7. Automatic projects

1. Add the source video.
2. Choose the source and target languages and recognition model.
3. Choose OmniVoice for local speech or Edge TTS for an online voice.
4. Decide whether to keep, blur or patch the original subtitles.
5. Keep the source sound or separate speech from the background.
6. Add music or a watermark if required.
7. Set the source, voice and music levels.
8. Start processing.

The command bar distinguishes model preparation from video processing. A model reaching the ready state does not complete the task progress bar. Pausing retains completed checkpoints; restarting deliberately discards results that depend on the restarted operation.

## 8. Manual editor

Manual tools are not numbered steps. Select any tool whose required input is available.

### Source

Replace the video from a file or link. **Keep original audio** uses the source track. **Separate vocals** runs Demucs and stores both the speech and background variants. Moving between variants reuses a valid saved result and does not start recognition.

### Recognition & translation

Choose the languages and recognition model, then run **Recognize and translate**. The result is timed subtitle text without a generated voice.

Running the command again replaces the subtitle text after confirmation. The existing subtitle style and position, source-subtitle treatment, watermark, music and levels remain unchanged. Generated speech is marked out of date because it no longer matches the new text.

### Subtitles

Select a clip on the timeline or click the subtitle in the result video. The editor opens the complete text for that segment.

- Type normally; Vietnamese IME composition is committed before save or focus changes.
- The draft saves 500 ms after typing stops and immediately when you click elsewhere.
- **Saving**, **Saved** or a retry message shows the actual state.
- Drag the subtitle on the video to move the project subtitle position.
- Drag its handle to change the project subtitle size.
- Drag a clip edge on the timeline to change its start or end time.

Clicking an empty part of the video saves the draft, removes text focus and hides the transform frame. Text changes make only that segment's voice out of date. Timing and style changes do not synthesize speech again.

Undo and Redo cover supported text, timing, picture, voice, sound and project-setting changes. They are separate from Back and Forward.

### Picture

Choose **Keep** to leave the source picture untouched, or **Conceal** and then choose **Blur** or **Patch**. Selecting concealment runs the required analysis only after the method has been chosen. The concealed region remains below the translated subtitle layer.

Watermark controls also belong here. Subtitle text and size are edited directly from the subtitle or the Subtitles tool, not from Picture.

### Voice

Before speech exists, select **Generate voice**. Once speech exists, use **Change voice** or **Regenerate**. These actions open a dialog; changing a field in the dialog does not alter the video until you confirm.

Choose **This segment** to affect only the selected subtitle or **Entire video** to use one voice throughout. Unchanged segments keep their valid audio. When multi-speaker recognition is off, regenerated segments use the same voice configuration as the rest of the video.

OmniVoice runs locally after its packs are installed. Edge TTS is an online provider and sends the text to that service. Voice samples in Automatic projects are prerecorded; opening a sample does not run a model.

### Sound

Source, voice and music level controls are always visible. Changes are heard against the current video without running translation or TTS. Add music from a local file or a supported link.

If a voice clip is missing, HaizFlow identifies the affected subtitle instead of creating it without confirmation.

### Export

Select **Export video** to render the current edit. Translated subtitles, concealed source subtitles, generated speech, music and watermark are optional. Export does not run an omitted AI tool on your behalf.

When the file is ready, the completion window offers **Play video**, **Open folder** and **Close**. The current output also remains available from the project toolbar.

## 9. Preview and timeline

The source and result players have separate play, pause, stop, mute and fullscreen controls. **Play both** starts them from the same position for comparison.

Drag the player slider, click the timeline or drag the playhead to seek. During dragging, the thumb follows the pointer immediately; player seeks are combined to keep the interface responsive. Releasing the pointer applies the exact final position.

When a preview source changes, the last valid frame remains visible until its replacement is ready. Background model work must not take ownership of the player or sound output.

## 10. Batch, Downloads and publishing

### Batch

Add videos, set the shared options and start the queue. Every row keeps its own status and progress. Retry a failed video without discarding successful outputs. A temporary per-video override does not silently become the base configuration for future imports.

### Downloads

- **Video:** inspect one URL, review its details and download it.
- **Channel:** inspect a public channel or profile, select items and add them to the queue.
- **Audio:** download supported audio or extract sound from a local media file.

Changing tabs does not reset the active request or queue.

### Social publishing

Connect Zernio, set the caption and post options, add an exported video, review the destination and confirm. This sends media to a third-party service. Review its terms, privacy rules, quotas and charges before use. A published item provides **Open post**.

## 11. Storage and cache

| Item | Current limit or rule |
| --- | ---: |
| Current verified Core artifact | 477 MiB |
| Core installation | Setup calculates the exact minimum; the current recommendation is 4 GiB free |
| Free space retained during resource installation | 2 GiB after download, installation and rollback estimates |
| Manual temporary data | 4 GiB per project; 16 GiB in total by default |

These Core figures do not include optional engines, models, source videos, exports or render temporary files. Resource packs and exports run their own free-space check using measured or estimated bytes.

Use **Settings → Clear temporary Manual data** to remove inactive previews, old mixes and other rebuildable data. The command must not remove source media, exports, the active edit or revisions required by Undo and Redo.

Source users may set `HAIZFLOW_HOME` in `.env` to place managed models, cache, data and temporary files under another local directory.

## 12. Common problems

### A model is being prepared

You may continue using the interface. Preparation and video processing have separate status messages. If preparation fails, open the technical log and check free space, network access, file verification and available RAM or VRAM.

### A public URL cannot be imported

Open it in a browser and confirm that it is still public. Private, removed, restricted or login-protected content needs the appropriate access; pressing the button repeatedly cannot bypass that restriction. For a temporary service error, wait briefly and try once more.

### The result has no sound

Check that the intended source, voice and music tracks exist, are not muted and have a non-zero level. In a Manual project, generating a voice and choosing the sound mix are separate actions.

### The result looks like the source for a moment

Wait for the saved preview to load. The result should keep its last valid frame and replace it only with a complete preview. If it remains incorrect, open the technical log and report the project state.

### Vietnamese input loses the last word

Current builds commit Windows IME text before saving. If this still occurs, report the Windows version, input method, affected field and exact text used to reproduce it.

### The application becomes slow

Stop jobs you no longer need, check available RAM/VRAM and free disk space, and clear inactive Manual data if the cache is full. Avoid editing an active project from a slow network location.

## 13. Report a problem

Open [GitHub Issues](https://github.com/MachHongHai/HaizFlow/issues) and include:

- the action you performed;
- what you expected and what happened instead;
- the visible error and a relevant excerpt from the technical log;
- Windows, GPU and HaizFlow versions;
- a small sample only when you have permission to share it.

Do not publish passwords, API keys, private links, complete project metadata or copyrighted media without permission.
