# Install HFlow

[Home](../README.md) · [User guide](user-guide.md) · [Tiếng Việt](install.vi.md)

## 1. Before you install

Use Windows 10 version 1809 or later, or Windows 11 x64, with at least 16 GB system RAM. An NVIDIA GPU is optional. GPU mode supports compatible 4 GB-class NVIDIA cards when CUDA reports at least 3.5 GiB dedicated VRAM. Shared graphics memory does not count toward this requirement. Internet access is needed to download the app and selected resource packs.

The 16 GB minimum means installed RAM (16 GiB DIMM capacity). Windows may reserve some RAM for hardware. HFlow measures installed and OS-usable RAM separately: a 16 GB installation is not rejected merely because Windows exposes about 13–14 GiB. If less than 8 GiB is OS-usable, check the hardware reservation before processing.

For a 16 GB CPU system, choose Whisper Small CPU, HY-MT2 CPU Q4 and OmniVoice CPU. Heavy models run sequentially to reduce memory use; voice generation retains the original model quality and may be slow. Close unnecessary apps, allow Windows to manage the page file and leave enough free disk space on its drive. HFlow checks available RAM and Windows commit headroom before each heavy stage. Installed capacity alone does not guarantee that every stage can run under current memory pressure. Saved results remain available when additional memory is needed.

Allow space for the app, packs, source videos and exports. Setup shows the requirement for its application build. Packs have separate requirements and may need temporary space for downloads, extraction or repair.

## 2. Install the app

**[Download HFlow-0.1.10-Setup.exe](https://github.com/MachHongHai/HaizFlow/releases/download/v0.1.10/HaizFlow-0.1.10-Setup.exe).** This is the only file you need to install the app. Core files on the [release page](https://github.com/MachHongHai/HaizFlow/releases/latest) are for automatic updates; do not download or extract them for installation.

1. Open **Setup.exe**, select the language and read the terms.
2. Choose an installation folder on a drive with enough free space.
3. Finish setup and open **HFlow** using its shortcut or **HFlow.exe**.

Python is not required. Do not open resource-pack executables directly or rearrange the application folders.

The current build is unsigned. Windows may show an unknown publisher or block execution. Verify the download source and author-provided SHA-256; do not disable antivirus or dismiss warnings for an unverified file. If your computer policy blocks unsigned applications, contact its administrator.

## 3. Choose CPU or GPU

Open **Settings → General**:

- **CPU:** for computers without a compatible NVIDIA GPU, or when using CPU models.
- **NVIDIA GPU:** for compatible hardware; GPU features also need their matching engine and model packs.

Choose **Apply** and review the project's models before processing. CPU users do not need a CUDA pack. Installing CUDA Toolkit manually is not necessary for the app's packaged engines.

On a 4 GB GPU with 16 GB RAM, start with Whisper Small GPU, HY-MT2 CPU Q4 (or Gemini) and OmniVoice GPU. The CUDA recognition and voice stages run sequentially; voice synthesis uses one sentence at a time without changing its checkpoint, FP16 precision or 32 inference steps. Whisper Turbo and full HY-MT2 GPU are unavailable on this profile. Demucs uses shorter GPU segments. Keep other GPU/CPU memory-intensive applications closed, and allow Windows to manage the page file. These settings reduce peak memory but do not guarantee every long project or busy 4 GB machine will fit.

## 4. Install the tools you need

Open **Settings → Resource packs** and choose **Install**:

For Douyin downloads, also install **Douyin browser (Chromium)** in the **Downloads** group. HFlow downloads it from the official Chromium source when you choose to install it; video, channel and audio use the same pack.

| Task | Resource |
| --- | --- |
| Speech recognition | Whisper Small or Whisper Turbo, in a supported processing mode |
| Local translation | HY-MT2 CPU or HY-MT2 GPU |
| Vocal separation | Demucs CPU or Demucs GPU, matching the app's mode |
| Original-caption detection | OCR |
| Local voice generation | OmniVoice and its matching processing environment |

The app lists the resources needed for each tool. Some resources are shared between packs; **Installed** means that resource is available and ready to use.

Wait for download, verification and installation to finish. **Pause** preserves downloaded data; **Continue** resumes it. The **…** menu provides **Check and repair** and **Remove pack** for resource management. Use these actions rather than manually deleting files inside a pack.

The project has one vocal-separation option, but Demucs has separate CPU/GPU packs. It follows the app's applied mode. Installing its GPU pack does not replace its CPU pack.

## 5. Add API keys only if needed

Local Whisper, HY-MT2, Demucs and OCR do not require Gemini or Zernio keys.

- **Gemini:** for Gemini translation.
- **Zernio:** for social publishing.

Open **Settings → API Key**, select a provider, add and check your keys. Zernio connection checks test the listed keys: green dots indicate valid keys; red dots indicate keys that need checking. Select the key to use.

Keys are stored in Windows Credential Manager. Never include them in screenshots, public logs or issues. You manage external service accounts and any associated charges.

## 6. Data and updates

Keep independent copies of important source and exported videos. Working data lives in the installation's runtime folder. Use **Move location** in Resource packs to move resource storage; let the operation finish and do not move folders during processing.

HFlow does not check for or download new versions. To upgrade, close HFlow, then run the new Setup and install into the same folder. The runtime folder is kept. Setup refuses to install a version older than the one in use.

## Start using HFlow

Follow the [User guide](user-guide.md) to create your first project, edit captions, dub and publish videos. [Help](support.md) covers resource management and contacting support.

**Voice licensing:** the current OmniVoice checkpoint is noncommercial. Read the [license and commercial-use notice](../README.md#license-and-commercial-use) before using it for monetized videos or client work.
