# Translation API connections

HaizFlow supports Gemini, OpenAI, DeepSeek, OpenRouter and custom
OpenAI-compatible **text translation** APIs. No API speech generation or voice
cloning is added by this feature. Zernio remains separate social-publishing configuration.

## Configure

Open Settings → API Key and choose a provider. Gemini and Zernio keep their
existing named-key workflows. For the other translation providers, add a
connection with a name and API key. API settings contain no model selection,
model-list loading or translation output options. A custom connection additionally
needs a Base URL. Model selection belongs to each project's **Model dịch** menu.
OpenAI and DeepSeek offer named presets in that menu. **Refresh models** fetches
the models available through the selected saved key;
OpenRouter lists text models declaring strict Structured Outputs support, plus
zero-priced text models declaring JSON mode (`response_format`) support. Legacy
OpenAI audio, image, embedding and incompatible chat-only models are omitted.
Search matches both the friendly name and exact model ID. Existing connections
are never migrated or silently changed to a different model. Saving a key does not
choose a model, and attempting to process without a project model is blocked.

Discovery is a bounded background GET request, not a paid translation. Changing
the provider, key or endpoint invalidates pending responses. Pagination limits or
network failure after some pages show a partial-list notice. Model-list presence
does not certify inference permission, endpoint compatibility or billing balance.
**Enter Model ID** in the project's provider menu is an advanced fallback, especially for custom APIs
without `/models`; users remain responsible for that model's JSON compatibility.
Official service URLs are fixed. Custom API connections additionally need a
Base URL (for example `https://api.example.com/v1`). The project's manual-model
dialog also offers a JSON output mode for custom APIs:

- JSON mode: `/chat/completions` with `response_format.type=json_object`.
- JSON Schema: strict subtitle schema; use only when the endpoint/model supports it.
- JSON by instruction: no `response_format` parameter, but the response must still
  be valid complete JSON with every requested subtitle ID.

In **Model dịch** in Manual, Auto or Batch, choose a provider first, then choose a
model inside its submenu. If several keys are saved, select a named connection
there. OpenAI/DeepSeek presets are immediately available; the refresh button loads
the catalogue for the selected saved key. A missing key links to API settings.
Changing models in a project never adds duplicate credential records or changes
another project's model. Existing
translation style, background and names/address guidance apply to all cloud
translation providers. Local HY-MT2 remains available without an API key.

The Check button calls only `/models`, without sending subtitles or invoking
inference. Success means authentication/model-list access, not validation of a
particular model; it does not guarantee billing balance or permission to run inference.
Some custom APIs do not expose model lists and cannot be verified this way.
Saving a connection does not require making a paid test translation.

## Data, costs and cache

- Keys are stored in Windows Credential Manager, not projects, JSON indexes,
  returned MCP model options or diagnostics. The local metadata index stores
  only connection ID, label, provider, endpoint, model and output format.
- Translation sends the requested subtitle text plus bounded context/guidance
  to the chosen provider. OpenRouter additionally routes to its backend provider;
  HaizFlow requests providers with `data_collection=deny` and parameter support
  by default. Nemotron 3.5 Super VL Free and Liquid LFM2.5 Free require data
  collection: selecting either opens a privacy warning before changing the model.
  Only explicit agreement stores a local grant for that connection ID and exact
  model; only that scope sends `data_collection=allow`. Cancel, X and Escape keep
  the old choice and create no grant. Existing selections without consent stop
  before sending subtitle content and ask the user to reselect. The grant contains
  no keys/media and survives restart; removing the connection removes its grants.
  All pickers (Manual, Auto, Batch and manual Model ID) share this flow. OpenRouter
  account-level privacy settings are not changed and can still reject routing.
  A data-policy HTTP 404 is explained as a privacy restriction, not a retired model.
- API charges and limits belong to the user's provider account. No automatic
  fallback to a different model/provider connection is performed. OpenRouter's
  own provider routing may use another endpoint for the same chosen model.
- A connection's endpoint/default model remain unchanged. Project model choices
  bind to a connection ID plus an explicit model override when necessary, not a
  global active key. Switching tabs, selecting a different model in another
  project or adding another key cannot redirect a queued project. Legacy choices
  without an override continue to use their saved connection's default model.
- Cache/progress/resume signatures include the connection configuration, model,
  source cues, target language and translation guidance. Valid completed batches
  survive pause; cancelled/discarded work follows the existing ownership cleanup.
- Missing/removed connections are reported, not silently replaced by HY-MT2.
  Keys/connections are local: moving a project to another machine requires
  configuring a connection there and selecting it again.
- Invalid, incomplete, refused or truncated answers cannot overwrite the final
  translation. Exact IDs, counts and non-empty strings are validated locally;
  timestamps are copied from the source, never generated by the API.
- Authentication, billing, rate-limit and unsupported-format errors are shown
  without raw response bodies or secrets. Lost/invalid POST responses are not
  automatically reissued as paid requests. Explicit transient HTTP server errors
  have at most three attempts. A later user-requested resume reuses accepted batches.
- HTTPS is required for remote custom endpoints; explicit loopback HTTP is
  allowed for local compatible servers. Credential-bearing redirects are blocked.

## Token use and safe retries

OpenRouter's model picker ships with a dated public snapshot (text translation
and supported JSON output only). It opens without a network request. A
successful explicit refresh replaces the local public catalogue; a partial one
merges, and failed/cancelled refreshes retain the previous list. The list survives
project switches and app restarts and contains no API keys/account data. Other
providers and custom endpoints never inherit this public OpenRouter catalogue.
The refresh button remains available because model availability and pricing can
change. OpenRouter rows show Free/Paid from public prompt/completion/request
prices, or Pricing unknown when pricing data is absent/invalid; a `:free` suffix
alone never overrides the published prices. These are last-known catalogue
labels, not a billing/quota check or an inference request.
Only OpenRouter's provider submenu has a local name/Model ID search; filtering
never makes a request or changes the saved model until the user selects a result.

Free JSON-mode models use `json_object` with a compact explicit output shape,
not an unsupported JSON Schema. The same exact-ID/count/non-empty-text checks
still apply; malformed results stop without an automatic generation retry.
Schema-capable models retain strict JSON Schema. Unknown manual IDs are never
silently downgraded. Public catalogue cache version 1 is ignored in favor of the
new bundled snapshot; project/media caches and credentials are not changed.

On 2026-11-02, the public catalogue did not list `deepseek/deepseek-r1:free`
or `deepseek/deepseek-r1-0528:free`, and their endpoint APIs returned empty lists,
despite historical free model pages remaining online. These unavailable IDs are
not added to the picker. OpenRouter HTTP 404 for a selected `:free` model explains
that no compatible endpoint is available and suggests refreshing/choosing another
free model. No fallback to paid models is sent. Current compatible additions are
`google/gemma-4-26b-a4b-it:free`, `google/gemma-4-31b-it:free` and
`recursive/flint-v1.0:free`. Public metadata is not an inference/quality guarantee;
provider policies, rate limits and availability still apply.

Protocol metadata now also retains bounded `context_length`, provider
`max_completion_tokens`, and a `user_only` prompt hint for Gemma chat templates.
Before requests are sent, output ceilings also reduce source batch size so a
smaller limit does not merely truncate the last subtitles. Small context windows
reserve half their capacity for input. All source IDs and guidance remain intact;
very long individual cues/guidance can still exceed a small model's window and
require choosing a larger-context model. No tokenizer-exact context estimate is
claimed. Gemma-family user-only prompts combine the instructions with the task
without discarding them; other chat formats retain their system/user messages.
Missing hints in an older public cache are enriched from the new bundled snapshot,
without changing credentials, selections, media caches or adding background GETs.

The 2026-11-03 controlled paid check used exactly two short requests to
`google/gemma-2-27b-it` (NextBit): an old payload and a corrected 2048-token,
user-only payload. Both returned HTTP 400. This model is therefore temporarily
excluded from recommendations and stops before inference if still saved in a
project; it is not described as retired or automatically replaced. Task-specific
UI-TARS, Schematron and Jev models/routers are also omitted from this subtitle
translation catalogue. Other models with low output limits are retained with
adaptive batch sizes. Presence is not a live-inference guarantee for all models.
Request logs include the exact model ID and safe rejection categories for HTTP
400/422 (context, output limit, role or JSON compatibility), never raw server text.

The 2026-11-03 endpoint audit covered all 363 shipped catalogue entries: the 344
concrete models had serving endpoints; 18 Latest aliases and one model router
had no direct provider entries, which does not by itself mean they are retired.
The two unavailable R1 Free IDs are filtered from discovery and old public caches.
OpenRouter's picker never re-inserts an unlisted saved/default model into its
catalogue; its existing project selection remains unchanged until the user chooses
another model. Advanced manual Model ID entry remains available. Pricing labels
reserve the checkmark column even on unselected rows so selection cannot shift them.

Projects have an inline reasoning control under Model dịch in Manual, Auto and
Batch settings. Vietnamese labels are “Mức” for effort levels and “Suy luận” for
reasoning switches/status. Choices are localized (Tắt, Bật, Tối thiểu, Thấp,
Trung bình, Cao, Rất cao, Tối đa); English UI keeps Level, Reasoning and the
English choice names. Stored/API values remain unchanged (`high`, `disabled`,
Gemini `thinkingLevel`). Switching UI language preserves the selected value.
For OpenRouter models advertising optional reasoning without effort levels,
Tắt/Bật maps to API booleans through `reasoning.enabled`.
The app explicitly defaults these models to `enabled: false`; `mandatory: false`
is not mistaken for reasoning being off. Unsupported values are omitted; changing models resets to
its compatible low-cost default. Unknown custom capabilities are not guessed.
OpenRouter's advertised supported efforts are kept as bounded public metadata,
separate from credentials and project/media caches, and survive app restarts.

The chosen value is stored per project/video, frozen into queued job settings,
and included in translation cache/checkpoint identity. Changing it does not
invalidate voice-only jobs. Legacy projects with no explicit selection retain
their previous default cache/resume identity. Selecting a higher effort gives
bounded extra output headroom (up to 32,768 tokens) only for that explicit choice;
this is a ceiling, not prepaid usage. Non-mandatory low-cost defaults retain the previous cap.

Models requiring reasoning, including OpenRouter's `deepseek/deepseek-r1-0528`,
need room for thinking as well as visible JSON. These requests use at most 12
sentences/2,000 source characters per batch, preserve the same cross-batch context
and checkpoint IDs, and add 8,192 tokens of headroom to the visible-output estimate
(combined ceiling 32,768; request timeout 240 seconds). Explicitly enabled optional
reasoning and models advertising reasoning support without usable control metadata
receive the same bounded reserve; optional models explicitly disabled do not.
Model-specific output/context ceilings still take precedence (for example, Liquid
Free's total output ceiling is 8,192). This does not force the
model to consume that ceiling, and is not a hard separate reasoning budget.
More batches can increase prompt overhead; actual total cost depends on the model.
`finish_reason=length` and all-reasoning/no-visible-output responses stop with a
specific token-limit error, without a paid automatic retry. Completed batches and
the previously published subtitles remain intact for an explicit resume.

OpenRouter currently advertises R1 0528 with `reasoning.mandatory=true` but no
`supported_efforts`. The project UI therefore shows only `reasoning: Enabled`,
without a fake Low/High selector or a disable option. Mandatory state survives
model discovery/restarts. An explicitly null `supported_efforts` means all gateway
efforts; an absent field means no effort selector, not an absence of reasoning.
An explicitly non-mandatory model can instead expose the boolean control above.
Never treat `reasoning.exclude`
as disabling reasoning: it hides the reasoning text, not its token consumption.

The 2026-11-03 free-catalogue audit covers all seven currently recommended free
models: Dots3-Note, Xing4.0, Nemotron 3.5 Super VL and both Gemma 4 variants have
optional reasoning controls; Flint V1 and LFM 2.5 2.6B require reasoning and expose
no fictitious disable/effort controls. Verification uses public metadata and fake
inference/native UI tests, not live generation using the user's API key. A provider
that ignores disable and returns almost all reasoning plus a few visible tokens
is diagnosed as reasoning-budget exhaustion, with no automatic regeneration.

- Provider model IDs retain exact case in project settings, processing, and resume
  checkpoints. Built-in local/Gemini enum names may still be normalized.
- Known OpenAI models use `none` reasoning where documented, otherwise the lowest
  supported effort (`low`/`minimal`). Current DeepSeek Flash/V4 presets explicitly
  disable their otherwise-enabled thinking mode. OpenRouter uses its unified
  reasoning control for these known models, without changing the chosen model.
  Unknown/custom models receive no guessed vendor-specific reasoning parameters.
- Output limits remain bounded and are not reduced merely to claim savings.
  Source cues, translation guidance, names/address context and strict completeness
  checks remain intact. No additional model calls are made for this optimization.
- Names, loanwords or numbers resembling the source do not alone trigger paid
  retranslation. Objectively malformed text still gets bounded recovery; a failed
  cloud recovery does not trigger another automatic paid recovery attempt.
- HTTP-200 responses containing provider errors are reported by their safe error
  category, not mislabelled as invalid subtitles. They are never automatically
  repeated because generation may already have incurred a charge. Lost/truncated
  responses also stop without blindly resubmitting; accepted batches remain saved.
- HTTP 429 does not by itself mean the user's daily quota is exhausted. Generic
  notices describe rate limiting/provider capacity without claiming quota exhaustion.
  OpenRouter's existing error response can distinguish explicit free daily/minute
  limits, insufficient-quota codes, or upstream provider hints; a bounded numeric
  Retry-After is shown when supplied. HTTP error bodies are capped at 64 KiB and
  only fixed local messages are displayed, never raw provider text or keys. This
  handling makes no quota/account GET requests, adds no retries, and does not
  change the selected model or enable a paid fallback.
- When a provider returns usage, technical logs show allowlisted input/output/
  reasoning token counts only, never keys or raw response contents. Reasoning is
  a subset of output tokens, not an extra amount to add again. Metrics logging
  failure cannot discard an already-paid response. Actual savings
  and translation quality require evaluation against a real user account/model.

## Protocol references

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [OpenRouter Structured Outputs](https://openrouter.ai/docs/guides/features/structured-outputs)

Automated tests use private credential stores and local/fake HTTP responses, not
user API keys or paid inference. Compatibility and translation quality should
also be evaluated against each user's chosen live model before production use.
