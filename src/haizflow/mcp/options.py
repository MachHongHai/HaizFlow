"""Small offline discovery snapshots shared by MCP commands; never fetch keys/models."""
from __future__ import annotations

from haizflow.services import translation_api_policy, translation_connections, translation_privacy


def validate_reasoning(choice, effort):
    if choice.startswith("api:"):
        translation_connections.resolve(choice)  # Never read credentials during configuration.
    info = translation_api_policy.project_configuration(choice, effort)
    allowed = info.get("values", []) + (["disabled"] if info.get("thinking") else [])
    if effort and effort not in allowed:
        raise ValueError("Unsupported reasoning level for this model. Read options(section='translation').")


def translation_settings(video):
    choice = video.translation_model
    privacy = {"required": False, "allowed": False}
    if choice.startswith("api:"):
        try:
            profile = translation_connections.resolve(choice)
            privacy = {"required": translation_privacy.required(profile),
                       "allowed": translation_privacy.allowed(profile)}
        except ValueError:
            pass  # Missing connection is still diagnosable from the stored model ID.
    return {
        "model": choice,
        "style": video.gemini_translation_style,
        "styles": ["balanced", "literal", "natural", "adaptive"],
        "selected_reasoning": video.translation_reasoning_effort,
        "reasoning": translation_api_policy.project_configuration(choice, video.translation_reasoning_effort),
        "data_collection": {**privacy, **({"notice":
            "This model's provider may collect prompt/output data. Review and accept its warning in HaizFlow first."}
            if privacy["required"] and not privacy["allowed"] else {})},
    }


def model_page(provider, connection_id, query, offset, limit, free_only):
    """Only return one filtered page of public catalogue metadata, with usable IDs."""
    from haizflow.services import translation_catalog_cache, translation_model_catalog
    from haizflow.services.gemini_translation import MODELS

    if connection_id:
        provider = translation_connections.get_connection(connection_id)["provider"]
    if provider == "gemini":
        rows = [{"value": model, "label": label} for model, label in MODELS.items()]
    elif provider == "openrouter":
        rows = translation_catalog_cache.load()
    else:
        rows = translation_model_catalog.presets(provider)
        if connection_id:
            profile = translation_connections.get_connection(connection_id)
            if profile["model"] and not any(row["value"] == profile["model"] for row in rows):
                rows.insert(0, {"value": profile["model"], "label": profile["model"]})
    rows = [row for row in rows if (not free_only or row.get("pricing_kind") == "free")
            and (not query or query.casefold() in (row["value"] + " " + row["label"]).casefold())]
    rows.sort(key=lambda row: (row.get("pricing_kind") != "free", row["label"].casefold()))
    items = []
    for row in rows[offset:offset + limit]:
        model = row["value"]
        profile = {"id": connection_id, "provider": provider, "model": model}
        needs_consent = translation_privacy.required(profile)
        items.append({
            "model": model, "label": row["label"],
            "value": f"api:{connection_id}:{model}" if connection_id else model,
            "pricing_kind": row.get("pricing_kind", "unknown"),
            "reasoning": translation_api_policy.capabilities(provider, model),
            **{key: row[key] for key in ("context_length", "max_completion_tokens") if key in row},
            **({"data_collection": {"required": True, "allowed": translation_privacy.allowed(profile),
                 "notice": "Provider may collect prompt/output data; explicit user consent is required."}}
               if needs_consent else {}),
        })
    return {"provider": provider, "connection_id": connection_id, "items": items,
            "total": len(rows), "offset": offset, "has_more": offset + len(items) < len(rows),
            "catalogue": "offline_cached" if provider == "openrouter" else "offline_presets",
            "requires_connection": provider != "gemini" and not connection_id,
            "availability": "Catalogue entries do not guarantee live endpoint availability or account quota."}


def subtitle_fonts(video, sample):
    from haizflow.core.subtitle_fonts import FONT_FILES, FONT_POLICY_VERSION, subtitle_font_for_text

    language = video.subtitle_language or video.target_language
    requested = video.subtitle_style.font_family
    return {"language": language, "requested": requested,
            "effective": subtitle_font_for_text(sample, language, requested),
            "families": list(FONT_FILES), "policy": FONT_POLICY_VERSION,
            "automatic_by_script": True, "fallback": "Whole-cue bundled Noto fallback for missing CJK glyphs."}
