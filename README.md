<div align="center">
  <img src="src/haizflow/desktop/assets/branding/haizflow-mark.png" width="96" alt="HaizFlow logo">
  <h1>HaizFlow</h1>
  <p><strong>Translate video. Edit captions. Finish your cut.</strong></p>
  <p>One Windows workspace for subtitles, voice and audio.</p>
  <p><a href="docs/install.md">Installation</a> · <a href="docs/user-guide.md">User guide</a> · <a href="https://github.com/MachHongHai/HaizFlow/issues">Support</a> · <a href="README.vi.md">Tiếng Việt</a></p>
</div>

## From the original video to your own edit

HaizFlow brings speech recognition, translation and caption editing into the same workspace. Add karaoke subtitles, voice, background music and a watermark, then preview and export your video.

Run the steps you select automatically, or work on each part independently in the Manual editor. Translation and voice generation are optional: you can use HaizFlow just to edit captions and mix audio.

## What can you do?

- **Translate and edit captions:** recognize speech with Whisper, translate locally with HY-MT2 or use Gemini with your own API key; adjust wording, timing, fonts and karaoke.
- **Finish the audio:** separate vocals with Demucs, adjust levels, add and loop music, and lower music under speech.
- **Create voice tracks:** use built-in voices, distinguish speakers for consistent voice assignments, or use a reference sample you have permission to use.
- **Edit the picture:** cover original captions with blur or background patching, add a watermark and compare against the original.
- **Work through a batch:** queue multiple videos, follow each result and retry failed work.
- **Prepare publishing:** import local files or supported links and connect Zernio for social publishing.

Review recognition, translation and speaker assignments before export, especially when speech overlaps or the recording is noisy.

## Get started

Version 0.1.0 is being tested ahead of release; a public installer for this version has not yet been approved. If you are testing a build supplied by the author, follow the [installation guide](docs/install.md). Once published, download from [official GitHub Releases](https://github.com/MachHongHai/HaizFlow/releases). Resource-pack executables are not application launchers.

1. Install and open HaizFlow. Vietnamese is the default; English is available in Settings.
2. Choose CPU or NVIDIA GPU in **Settings → General**, then install the resource packs you need.
3. Start a **Manual** project to learn each tool, or an **Automatic** project to run your selected workflow.
4. Review the translation, captions and sound. Choose **Export** to save the video to your own folder.

## Runs on your computer

HaizFlow supports Windows 10 version 1809 or later and Windows 11, x64. Installer users do not need Python. CPU-only computers can open the app and use supported CPU options; GPU features require compatible NVIDIA hardware and their matching packs.

Local tools run on your computer after their packs are installed. Internet access is needed for downloads, updates, importing links and online services. Gemini, Zernio and other external services have their own terms, limits and charges.

The installer shows the application space requirement. Resource packs, projects and exported videos need additional space. You can move resource storage in Settings. [Learn how to choose packs and manage storage](docs/install.md).

## Commercial content

HaizFlow is free to use under its [application license](LICENSE). Video, music, voice samples and models have separate rights and conditions.

**The current OmniVoice checkpoint is restricted to noncommercial use.** Do not assume it is licensed for monetized videos, advertising or client work without suitable permission. Free application access and public source code do not grant commercial model rights. Other tools also have their own licenses; HaizFlow does not claim that every workflow is commercially cleared.

## Guides and support

- [Installation](docs/install.md): CPU/GPU, resource packs, API keys and data.
- [User guide](docs/user-guide.md): your first project, captions, voice and export.
- [Report an issue](https://github.com/MachHongHai/HaizFlow/issues): include steps, version and a screenshot; never include API keys.
- [Development guide](docs/development.md) and [architecture](docs/architecture.md): for contributors and maintainers.

Created by **Mạch Hồng Hải (Mach Hong Hai)**. If HaizFlow helps your workflow, [star the repository](https://github.com/MachHongHai/HaizFlow) or share feedback.

### License and notices

HaizFlow Source-Available 1.0 is not an OSI open-source license. Redistribution, repackaging and commercial software restrictions are set out in [LICENSE](LICENSE). See [NOTICE](NOTICE) and [third-party notices](THIRD_PARTY_NOTICES.md). [Inactive draft terms](legal/LICENSE-SOURCE-AVAILABLE-DRAFT.md) and the [licensing review](docs/licensing-review.md) are retained separately for maintainers.
