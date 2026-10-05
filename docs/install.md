# Install HaizFlow

[Home](../README.md) · [User guide](user-guide.md) · [Tiếng Việt](install.vi.md)

## 1. Before you install

Use Windows 10 version 1809 or later, or Windows 11 x64. An NVIDIA GPU is optional. Internet access is needed to download the app and selected resource packs.

Allow space for the app, packs, source videos and exports. Setup shows the requirement for its application build. Packs have separate requirements and may need temporary space for downloads, extraction or repair.

## 2. Install the app

Version 0.1.0 is currently being tested and is not publicly released. Testers should use the installer supplied by the author. Once published, download only from [official GitHub Releases](https://github.com/MachHongHai/HaizFlow/releases).

1. Open **Setup.exe**, select the language and read the terms.
2. Choose an installation folder on a drive with enough free space.
3. Finish setup and open **HaizFlow** using its shortcut or **HaizFlow.exe**.

Python is not required. Do not open resource-pack executables directly or rearrange the application folders.

The current build is unsigned. Windows may show an unknown publisher or block execution. Verify the download source and author-provided SHA-256; do not disable antivirus or dismiss warnings for an unverified file. If your computer policy blocks unsigned applications, contact its administrator.

## 3. Choose CPU or GPU

Open **Settings → General**:

- **CPU:** for computers without a compatible NVIDIA GPU, or when using CPU models.
- **NVIDIA GPU:** for compatible hardware; GPU features also need their matching engine and model packs.

Choose **Apply** and review the project's models before processing. CPU users do not need a CUDA pack. Installing CUDA Toolkit manually is not necessary for the app's packaged engines.

## 4. Install the tools you need

Open **Settings → Resource packs** and choose **Install**:

| Task | Resource |
| --- | --- |
| Speech recognition | Whisper Small or Whisper Turbo, in a supported processing mode |
| Local translation | HY-MT2 CPU or HY-MT2 GPU |
| Vocal separation | Demucs CPU or Demucs GPU, matching the app's mode |
| Original-caption detection | OCR |
| Local voice generation | OmniVoice and its matching processing environment |

The app identifies missing dependencies. Existing packs may already supply some resources, so **Installed** does not necessarily mean you downloaded a separate pack yourself.

Wait for download, verification and installation to finish. **Pause** preserves valid download data; **Continue** resumes it. For damaged packs, use **… → Check and repair**. You can remove and reinstall a pack or repair it; avoid manually deleting files inside it.

The project has one vocal-separation option, but Demucs has separate CPU/GPU packs. It follows the app's applied mode. Installing its GPU pack does not replace its CPU pack.

## 5. Add API keys only if needed

Local Whisper, HY-MT2, Demucs and OCR do not require Gemini or Zernio keys.

- **Gemini:** for Gemini translation.
- **Zernio:** for social publishing.

Open **Settings → API Key**, select a provider, add and check your keys. Zernio connection checks test the listed keys: green dots indicate valid keys; red dots indicate failures. Select the key to use.

Keys are stored in Windows Credential Manager. Never include them in screenshots, public logs or issues. You manage external service accounts and any associated charges.

## 6. Data and updates

Keep independent copies of important source and exported videos. Working data lives in the installation's runtime folder. Use **Move location** in Resource packs to move resource storage; let the operation finish and do not move folders during processing.

Update checks notify you when a new version is available. Confirm the download, then confirm restarting to apply it. Finish or stop active work before updating. A public GitHub update has not yet been available for end-to-end testing.

## If a tool will not run

1. Check the applied CPU/GPU mode and matching pack.
2. Install or repair any missing pack in Settings. Warnings do not automatically take you away from the project.
3. Check free space, network access and folder write permissions.
4. For memory errors, close other apps or choose a smaller model; you can turn off **Keep models ready**.
5. [Report the issue](https://github.com/MachHongHai/HaizFlow/issues) with the version, steps and error. Do not include keys or private media.

**Voice licensing:** the current OmniVoice checkpoint is noncommercial. Read the [commercial-content notice](../README.md#commercial-content) before using it for monetized videos or client work.
