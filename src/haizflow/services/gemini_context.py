"""Bounded, project-local translation context; no additional model requests."""

VERSION = "gemini-consistent-dialogue-v3-style-default-sampling"
MAX_GUIDANCE = 4000
STYLE_PROMPTS = {
    "balanced": "Use clear, neutral subtitle phrasing, balancing fidelity and readability.",
    "literal": "Stay close to the source wording and register; avoid embellishment or unnecessary paraphrasing.",
    "natural": "Use idiomatic, conversational target-language phrasing rather than source-language syntax.",
    "adaptive": "Adapt idioms, humor and emotional delivery for the target audience without adding facts or intensifying the source tone.",
}


def signature_parts(video):
    if not str(getattr(video, "translation_model", "")).startswith("gemini-"):
        return ()
    return (VERSION, str(getattr(video, "gemini_translation_instructions", "") or "").strip(),
            str(getattr(video, "gemini_translation_glossary", "") or "").strip(),
            str(getattr(video, "gemini_translation_style", "balanced") or "balanced"))


def guidance(video):
    parts = signature_parts(video)
    return {"translation_instructions": parts[1], "translation_glossary": parts[2],
            "translation_style": parts[3]} if parts else {}


def request_context(texts, translations, indices):
    """Reconstruct memory from durable accepted translations, also on retry."""
    requested = set(indices)
    if not requested:
        return {}
    indices = sorted(requested)
    accepted = [index for index, value in enumerate(translations) if value and index not in requested]
    # Early anchors keep names established at the start; recent examples keep
    # the current relationship/scene. Never assume all speakers share pronouns.
    prior = [index for index in accepted if index < indices[0]]
    following = [index for index in accepted if index > indices[-1]]
    examples = sorted(set(accepted[:4] + prior[-6:] + following[:2]))
    neighbors = sorted(set(range(max(0, indices[0] - 3), indices[0]))
                       | set(range(indices[-1] + 1, min(len(texts), indices[-1] + 4))))
    return {
        "accepted_examples": [{"source_id": index, "source": str(texts[index])[:240],
                               "translation": str(translations[index])[:240]} for index in examples],
        "neighboring_source": [{"source_id": index, "text": str(texts[index])[:240]} for index in neighbors],
    }
