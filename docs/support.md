# HaizFlow help

[Home](../README.md) · [Installation](install.md) · [User guide](user-guide.md) · [Tiếng Việt](support.vi.md)

## Resource packs

Open **Settings → Resource packs** to install, check or remove packs. The CPU/GPU mode in **Settings → General** determines the resources used for processing.

- For a missing-pack notification, install the named pack, then run the tool again.
- For installed packs, use **… → Check and repair** to verify files and the processing environment.
- Use **Pause/Continue** to manage downloads. Valid downloaded data is retained.
- To reinstall from scratch, choose **Remove pack**, then **Install**.

Another pack may already provide a shared resource. **Installed** indicates readiness, not how many times you downloaded an individual pack. Do not manually delete files inside packs.

## API keys

In **Settings → API Key**, check that the complete key is pasted and the correct account is selected. A red Zernio dot means the check did not succeed: review the key, permissions and network connection, then check again.

Keys are stored in Windows Credential Manager for the current Windows account. Add them again when changing computers or Windows accounts. Never send keys in screenshots, logs or support requests.

## Audio and preview

Check the source, voice and music tracks on the timeline. Enable the tracks you want to hear and adjust their levels. Avoid playing original and dubbed speech together unless intended.

Captions use the bundled Bangers font. Review their position, size and caption area at several points in the video.

## Memory and storage

For RAM/VRAM notifications, close other apps or choose a smaller model suitable for your computer. Turn off **Keep models ready** to release models between processing runs if needed. This setting reduces repeated loading; it does not increase your computer's memory.

Use **Move location** in Resource packs to relocate resources. Let the operation finish and keep independent copies of important source videos and exports. Do not manually delete project folders or packs in use.

## Windows and installation

The installer is unsigned. Windows may show an unknown publisher or apply a policy that blocks unsigned apps. Verify the official download source and SHA-256; do not disable antivirus or add broad exclusions. Contact the administrator of an organization-managed computer.

## Contact support

Open a request on [GitHub Issues](https://github.com/MachHongHai/HaizFlow/issues) and include:

1. Your HaizFlow and Windows versions.
2. The steps and tool/model name.
3. A notification screenshot or relevant log with private information removed.
4. Your CPU/GPU mode and resource-pack status.

Do not share API keys, cookies, account details or private videos. Share only media you have permission to provide.
