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

In **Settings → API Key**, check the complete key and choose **Use** for the intended account. Each provider selects its active key here; translation models are chosen inside projects. **Check connection** contacts the service again, but success does not guarantee model availability or remaining credit. See the [API guide](translation-api.md).

Keys are stored in Windows Credential Manager for the current Windows account. Add them again when changing computers or Windows accounts. Never send keys in screenshots, logs or support requests.

## Audio and preview

Check the source, voice and music tracks on the timeline. Enable the tracks you want to hear and adjust their levels. Avoid playing original and dubbed speech together unless intended.

Choose a bundled font with its preview; Chinese, Japanese and Korean have suitable regional fallbacks. Review position, size and caption area at several points in the video. To correct a voice without regenerating the whole video, select the affected sentences in Manual's voice-generation scope.

## Memory and storage

If a GPU model is unavailable, check the NVIDIA driver and matching resource packs. Choose a smaller supported model when necessary; having a compatible GPU does not mean every model fits its memory.

For RAM/VRAM notifications, close other apps or choose a smaller model suitable for your computer. Turn off **Keep models ready** to release models between processing runs if needed. This setting reduces repeated loading; it does not increase your computer's memory.

Having enough installed RAM is different from having enough free memory right now. If the app asks for more memory, free some resources or choose a smaller model, then continue from the valid saved results.

OmniVoice CPU can take minutes for a long sentence. If progress seems stuck, open **Details** to inspect the technical log before restarting. For faster synthesis, use a compatible GPU option with enough available memory.

Use **Move location** in Resource packs to relocate resources. Let the operation finish and keep independent copies of important source videos and exports. Do not manually delete project folders or packs in use.

## MCP connection

Keep HaizFlow open and enable **Settings → MCP**. **Check HaizFlow** checks the app side; then send the test prompt from your agent. If you moved or updated HaizFlow, copy the current connection details again. Do not use a normal GUI launch command as an MCP server. See the [MCP guide](mcp.md).

## Error notifications

Read the short notification first. **Details** opens the technical log; **Confirm** or the close button dismisses the notification. The project's **…** menu also provides technical logs. Include only the relevant, redacted portion when contacting support.

## Windows and installation

The installer is unsigned. Windows may show an unknown publisher or apply a policy that blocks unsigned apps. Verify the official download source and SHA-256; do not disable antivirus or add broad exclusions. Contact the administrator of an organization-managed computer.

## Contact support

Open a request on [GitHub Issues](https://github.com/MachHongHai/HaizFlow/issues) and include:

1. Your HaizFlow and Windows versions.
2. The steps and tool/model name.
3. A notification screenshot or relevant log with private information removed.
4. Your CPU/GPU mode and resource-pack status.

Do not share API keys, cookies, account details or private videos. Share only media you have permission to provide.
