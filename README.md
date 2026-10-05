<div align="center">
  <img src="src/haizflow/desktop/assets/branding/haizflow-mark.png" width="96" alt="HaizFlow logo">
  <h1>HaizFlow</h1>
  <p><strong>A free Windows app for downloading, translating, subtitling and dubbing videos.</strong></p>
  <p><a href="docs/install.md">Installation</a> · <a href="docs/user-guide.md">User guide</a> · <a href="https://github.com/MachHongHai/HaizFlow/issues">Report an issue</a> · <a href="README.vi.md">Tiếng Việt</a></p>
</div>

## About HaizFlow

HaizFlow helps you download videos, translate speech, create subtitles and add translated voice tracks. Process one video or a batch, cover original subtitles and assign different voices to different speakers. You can publish processed videos to social media through Zernio.

Automatic mode runs the steps you select. The Manual editor lets you review and correct captions or voice tracks before exporting.

## Main features

| Feature | What you can do |
| --- | --- |
| **Batch video downloads** | Select multiple videos from supported public channels or profiles and queue them for download. |
| **Video translation** | Recognize speech with Whisper; translate locally with HY-MT2 or use Gemini. Review translations before exporting. |
| **Subtitle creation** | Create captions from video speech; edit text, timing, fonts and karaoke highlighting. |
| **Video dubbing** | Generate speech for translated text using built-in voices or a reference sample you have permission to use. |
| **Automatic processing** | Choose languages, models and voice settings, then run your selected recognition, translation, dubbing and caption-coverage steps. |
| **Batch processing** | Apply common settings to multiple videos, track each result and rerun failed videos. |
| **Cover original subtitles** | Detect caption regions with OCR and cover them using blur or background patching. |
| **Multiple-speaker detection** | Group speakers and assign a separate voice to each group instead of using one voice for the entire conversation. |
| **Social publishing** | Select an account, prepare the post and publish through Zernio. You can use processed videos directly from projects. |

Manual tools run independently: dubbing is optional when you only need translated captions.

Recognition, translation and speaker detection can make mistakes, particularly with noise or overlapping speech. Review results before exporting or publishing.

## Local translation without per-call API charges

Whisper and HY-MT2 run on your computer after their resource packs are installed. They do not require API keys or per-call translation fees. Gemini is an additional option for online translation.

Computers without an NVIDIA GPU can use supported CPU options. Compatible NVIDIA GPUs can use GPU models. CPU/GPU resources are packaged separately, and the app warns when a required pack is missing.

Gemini, Zernio and other external services have their own terms, limits and charges. OmniVoice has the usage restriction described below.

## Install and get started

Version 0.1.0 is being tested and is not publicly released yet. Testers should use the installer supplied by the author. Once available, download from [official GitHub Releases](https://github.com/MachHongHai/HaizFlow/releases).

1. Install and open HaizFlow. Vietnamese is the default; English is available in Settings.
2. Choose CPU or NVIDIA GPU in **Settings → General**, then install the resource packs you need.
3. Create an **Automatic**, **Manual** or **Batch** project and add videos.
4. Select language, models and voice if needed. Process, review and **Export** the video.

Supported systems are Windows 10 version 1809 or later and Windows 11 x64, with at least 16 GiB RAM. Installer users do not need Python. Resource packs, projects and exports need additional storage; Setup and the Resource packs page show their corresponding requirements.

See [Installation](docs/install.md) for CPU/GPU packs, API keys and storage. See the [User guide](docs/user-guide.md) for projects, captions, dubbing and publishing.

## License and commercial use

HaizFlow is free to use under [HaizFlow Source-Available 1.0](LICENSE). This is not an OSI open-source license. Redistribution, repackaging and commercial software conditions are specified in LICENSE.

**The current OmniVoice model is licensed for noncommercial use only.** Do not assume it can be used for advertising, monetized videos or client work without appropriate permission. HaizFlow's license does not replace the model license.

You need permission to use imported video, music and voice samples. See [NOTICE](NOTICE) and [third-party notices](THIRD_PARTY_NOTICES.md). The [licensing review](docs/licensing-review.md) and [inactive draft terms](legal/LICENSE-SOURCE-AVAILABLE-DRAFT.md) are retained separately.

## Support and contributions

[Report a problem or suggest a change](https://github.com/MachHongHai/HaizFlow/issues) with the version, steps and error screenshot. Never include keys or private data.

Source installation, testing and packaging are covered in the [development guide](docs/development.md). See the [technical documentation](docs/README.md) to contribute code.

Created by **Mạch Hồng Hải (Mach Hong Hai)**. [Star the repository](https://github.com/MachHongHai/HaizFlow) to follow the project.
