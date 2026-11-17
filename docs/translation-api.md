# Translation APIs

[Home](../README.md) · [User guide](user-guide.md) · [Tiếng Việt](translation-api.vi.md)

HaizFlow supports Gemini, OpenAI, DeepSeek, OpenRouter and custom OpenAI-compatible APIs for **translation**. Voice generation is configured separately. Zernio is for social publishing.

## 1. Add and select an API key

1. Open **Settings → API Key** and choose a provider.
2. Add a name and key. For a custom API, also enter its Base URL.
3. Choose **Check connection** beside that key.
4. Choose **Use** for the key you want HaizFlow to use.

Each provider has its own selected key. When you add more keys, choose the one to use in Settings—not inside individual projects. Changing that selection applies to subsequent work with that provider; it does not change a job already started.

Keys are saved in Windows Credential Manager. Do not share them in screenshots or support requests.

## 2. Choose a model inside the project

In Manual, Automatic or Batch settings, open **Translation model**, choose a provider, then choose its model.

![Project model picker with OpenRouter search and free-model labels](images/screenshots/translation-models-1.0.6.png)

Model selection belongs to the project, not the API Key page. If no key is selected, return to Settings to add or select one.

OpenRouter includes search and a refresh button. Its last available list opens immediately; refresh when you want an updated list. **Free**, **Paid** and **Pricing unknown** describe the last known catalogue information, not your remaining quota. A free model can still be busy, restricted or temporarily unavailable. HaizFlow does not silently switch to a paid model.

Use **Enter Model ID** when a compatible model is not listed. The ID must match your provider's spelling exactly; entering an ID does not guarantee the server supports it.

## 3. Choose style and reasoning

Open **Style & guidance** to choose a translation style and add context or character/address conventions. A natural dialogue style is often suitable for conversations; use a literal style when staying close to the source matters more.

The **Level** or **Reasoning** control appears only when supported by the selected model. Style and reasoning are separate: changing style does not raise reasoning. Higher reasoning may take longer and use more tokens; it does not guarantee a better translation. Models that require reasoning cannot have it disabled.

## Custom APIs and Ollama

Custom connections support OpenAI-compatible Chat Completions, including compatible local Ollama servers.

- Remote example: `https://api.example.com/v1`.
- Local Ollama example: `http://localhost:11434/v1`.
- Enter the Base URL only, without `/chat/completions` or `/responses`.
- Use your server's key. If a local Ollama server does not check keys, the required key field can contain a placeholder such as `ollama`.
- Choose a model already available on that server. HaizFlow does not download Ollama models for you.

The project's manual model dialog offers JSON mode, JSON Schema and JSON by instruction. Choose a format your server/model supports. A server reachable without authentication is shown as reachable, not as proof that its key is valid.

## What connection checking means

Checks contact the service again; they do not just reuse a green status or a public model list. They do not run a sample translation or consume generation tokens.

A successful check confirms the access tested at that time—not that every model is available, billing is funded or a long translation will succeed. Some custom servers do not offer the check endpoint even though translation can work. Model-list refresh is also separate from a key check.

## Costs, privacy and errors

- External services set their own prices, quota and data policies. Free/Paid labels are guidance, not a billing guarantee.
- Translation sends subtitles and your guidance to the chosen service. Review OpenRouter's data-collection warning when shown; consent is specific to that connection and model.
- HaizFlow uses provider-default output budgets rather than a guessed app-wide token ceiling. Provider limits still apply; reasoning can increase usage and waiting time.
- Work is translated in groups. Completed groups are saved so a supported resume can reuse them.
- Rate limiting does not necessarily mean you used up your daily quota. Capacity, account access and provider restrictions can also cause a failure.
- If a response is incomplete or cannot be safely matched to the requested captions, it is not accepted as a finished translation. Review the notification and choose **Details** for technical logs.
- Pausing stops the active request locally. It cannot guarantee that a provider stops work or waives a charge for a request already received.

For local translation without an API key, choose HY-MT2.

## Further reading

[Style and guidance](gemini-translation-guidance.md) · [MCP](mcp.md) · [Help](support.md)

Implementation notes: [provider-default output budgets](translation-provider-default-budgets-20261117.md) and [OpenRouter audit](openrouter-project-c-audit-20261117.md). Dated audit results describe those tests, not a permanent list of available models.
