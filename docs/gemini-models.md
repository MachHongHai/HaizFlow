# Gemini translation catalogue

Reviewed 2026-11-15 against Google's [model catalogue](https://aistudio.google.com/docs/models),
[thinking levels](https://aistudio.google.com/docs/thinking#thinking-levels), and a real
`GET /v1beta/models` using the configured key. Only text-translation models are offered.
Image, TTS, audio, robotics, custom-tools variants, floating `latest` aliases and deprecated
redirects (`gemini-3.5-flash`, `gemini-3.7-flash`) are not added.

The single source is `haizflow.core.gemini_models`, shared by schemas, persisted projects,
batch settings, the project picker, translation requests and MCP discovery. No extra model
picker is added to API-key settings. Preview names are explicit. No model is substituted
automatically. Lowest supported reasoning is the app default; style does not raise it.

## Live compatibility check

Synthetic English → Vietnamese, natural style, three short cues per model, normal production
JSON schema and parser, lowest supported reasoning. One POST per model, without automatic
retries. No project subtitles, files, settings or credentials were changed.

| Model | Result with the configured account |
| --- | --- |
| Gemini 3.1 Flash-Lite | Passed; all 3 IDs and Vietnamese translations |
| Gemini 3.5 Flash-Lite | Passed; all 3 IDs and Vietnamese translations |
| Gemini 3.6 Flash | Passed; all 3 IDs and Vietnamese translations |
| Gemini 3.8 Flash | Read timeout at 60s; second probe with one cue also timed out at 90s |
| Gemini 4 Hydrogen | Passed; all 3 IDs and Vietnamese translations |
| Gemini 4 Argon | HTTP 429: free-tier allocation is 0 for this key |
| Gemini 4 Carbon | HTTP 429: free-tier allocation is 0 for this key |
| Gemini 3 Flash Preview | Passed; all 3 IDs and Vietnamese translations |
| Gemini 3.1 Pro Preview | HTTP 429: free-tier allocation is 0 for this key |

Successful probes reported the exact requested model ID. This is a small protocol check,
not a quality benchmark or a guarantee of quota/availability on other accounts. A timeout
does not establish model retirement; 3.8 Flash remains officially supported. Models without
free quota stay selectable for accounts with the required billing/access. Zero free quota
is explained without retrying the same request or suggesting that waiting must fix it.

Gemini 4 Hydrogen supports Low/Medium/High/Xhigh; Carbon and Argon support Low/Medium/High.
The picker retains its existing compact layout, with economical Flash-Lite choices first.

## Pricing labels

Checked against [Google's standard GenerateContent pricing](https://aistudio.google.com/docs/pricing)
on 2026-11-15. Flash-Lite 3.1/3.5, Flash 3.6/3.8, Hydrogen and Flash Preview have a free
tier; Argon, Carbon and Pro Preview are paid-only. The project picker and MCP share this
metadata. “Miễn phí” denotes free-tier availability, not guaranteed zero cost or remaining
quota for a particular key. A short hover hint and the existing billing notice retain this
distinction without adding permanent explanatory text. No account quota is fetched.
