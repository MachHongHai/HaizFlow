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

Whisper selects precision from the GPU capabilities reported by CTranslate2. FP16-capable GPUs keep FP16; older GPUs such as the GTX 1070 use INT8/FP32 when supported by the backend. This does not change checkpoints or force all machines to CPU. Recognition logs show the selected mode. Compatible drivers and GPU runtimes are still required; compatibility mode does not guarantee that every model fits in VRAM.

For RAM/VRAM notifications, close other apps or choose a smaller model suitable for your computer. Turn off **Keep models ready** to release models between processing runs if needed. This setting reduces repeated loading; it does not increase your computer's memory.

Installed RAM determines minimum CPU eligibility; currently available RAM and Windows commit headroom determine whether a model can be loaded now. Before CPU HY-MT2, unused warm-up runtimes are released and low memory is remeasured for up to two seconds. If budgets remain insufficient, processing stops safely while retaining completed results; memory validation is not bypassed.

OmniVoice CPU can take minutes for a long sentence. Completion percentage increases only after valid audio exists; `decoder_forwards` diagnostics report actual inference activity rather than timer heartbeats. Precision and inference steps are unchanged. GPU-to-CPU recovery changes only the recovering invocation's backend, not saved model choices or valid checkpoints.

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
