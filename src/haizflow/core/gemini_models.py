"""Curated text-translation models; verified against Google docs on 2026-11-15.

https://aistudio.google.com/docs/models
https://aistudio.google.com/docs/thinking#thinking-levels
https://aistudio.google.com/docs/pricing
Do not add media models, floating latest aliases, or retired redirect aliases.
"""

# Order is shared by project pickers and MCP. Keep economical models first.
MODEL_LABELS = {
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
    "gemini-3.6-flash": "Gemini 3.6 Flash",
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-4-hydrogen": "Gemini 4 Hydrogen",
    "gemini-4-argon": "Gemini 4 Argon",
    "gemini-4-carbon": "Gemini 4 Carbon",
    "gemini-3-flash-preview": "Gemini 3 Flash Preview",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
}

_LEVELS = ("low", "medium", "high")
FREE_TIER_MODELS = frozenset({
    "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.6-flash",
    "gemini-3.8-flash", "gemini-4-hydrogen", "gemini-3-flash-preview",
})
PAID_ONLY_MODELS = frozenset({"gemini-4-argon", "gemini-4-carbon", "gemini-3.1-pro-preview"})
THINKING_LEVELS = {
    model: (("minimal",) + _LEVELS if model in {
        "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3-flash-preview",
    } else _LEVELS + ("xhigh",) if model == "gemini-4-hydrogen" else _LEVELS)
    for model in MODEL_LABELS
}


def model_options() -> list[dict[str, str]]:
    # "free" means a free tier exists, not that a billing-enabled key is unbilled.
    return [{"value": model, "label": label,
             "pricing_kind": "free" if model in FREE_TIER_MODELS else "paid" if model in PAID_ONLY_MODELS else "unknown"}
            for model, label in MODEL_LABELS.items()]
