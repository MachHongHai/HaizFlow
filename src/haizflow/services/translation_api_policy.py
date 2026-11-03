"""Conservative, model-specific token policy for subtitle translation only."""
from __future__ import annotations

import re

EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def output_limit(base: int, effort: str = "") -> int:
    """Only an explicit higher effort increases bounded reasoning/output headroom."""
    return max(base, {"medium": 8192, "high": 16384, "xhigh": 24576, "max": 32768}.get(effort, base))


def request_limits(provider: str, model: str, base: int, effort: str = "") -> dict:
    """Leave visible-output headroom when reasoning may run, without paid retries.

    This is a combined output ceiling, not an enforceable separate reasoning
    budget. R1 exposes neither effort levels nor reasoning.max_tokens controls.
    Optional boolean controls default off; enabled or undisablable reasoning
    receives bounded headroom. Unknown non-reasoning models keep their policy.
    """
    info = capabilities(provider, model)
    mandatory = info.get("mandatory", False)
    effective = effort or info.get("default", "")
    active_reasoning = bool(mandatory or provider == "openrouter" and info
                            and effective not in {"none", "disabled"})
    if provider == "openrouter" and not info:
        from haizflow.services.translation_catalog_cache import protocol_for

        active_reasoning = bool(protocol_for(model).get("reasoning_supported"))
    limit = output_limit(base, effort)
    if active_reasoning:
        limit = min(32768, max(limit, base + 8192))
    sentences, characters = (12, 2000) if active_reasoning else (24, 4000)
    if provider == "openrouter":
        from haizflow.services.translation_catalog_cache import protocol_for

        protocol = protocol_for(model)
        ceilings = [value for value in (protocol.get("max_completion_tokens"),
                    protocol.get("context_length", 0) // 2) if type(value) is int and value > 0]
        if ceilings:
            ceiling = min(ceilings)
            limit = min(limit, ceiling)
            # Split before sending, rather than just clamping output and losing
            # the last subtitles. Match the visible-output estimator's reserve.
            if ceiling < 8192:
                characters = min(characters, max(32, (ceiling - 1024) // 4))
                sentences = min(sentences, max(1, (ceiling - 1024) // 64))
    return {"max_tokens": limit, "sentences": sentences,
            "characters": characters, "timeout": 240 if active_reasoning else 90,
            "mandatory": bool(mandatory), "reasoning_active": active_reasoning}


def capabilities(provider, model, *, has_guidance=False):
    """Official parameter names/values only; unknown capabilities stay hidden."""
    name = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model.lower())
    if provider == "gemini" and model in {"gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash"}:
        values = ["low", "medium", "high"]
        if model != "gemini-3.8-flash":
            values.insert(0, "minimal")
        return {"parameter": "thinkingLevel", "values": values,
                "default": "low" if has_guidance else values[0]}
    if provider == "deepseek" and name in {"deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash"}:
        return {"parameter": "reasoning_effort", "values": ["low", "high", "max"],
                "thinking": True, "default": "disabled"}
    if provider == "openai" and _openai_effort(name):
        lowest = _openai_effort(name)
        values = ["low", "medium", "high"]
        if name.startswith("gpt-6") or name.startswith("gpt-5.6"):
            values += ["xhigh", "max"]
        if lowest in {"none", "minimal"}:
            values.insert(0, lowest)
        return {"parameter": "reasoning.effort", "values": values, "default": lowest}
    if provider == "openrouter":
        from haizflow.services.translation_reasoning_catalog import get
        # The dated R1 and original aliases require reasoning but do not expose
        # selectable effort levels. Keep this known fallback across restarts.
        r1 = model.removesuffix(":free").removesuffix(":nitro") in {
            "deepseek/deepseek-r1", "deepseek/deepseek-r1-0528"}
        cached = get(model)
        if r1:
            cached = {**(cached or {"parameter": "reasoning", "values": [], "default": ""}), "mandatory": True}
            cached["values"] = [value for value in cached["values"] if value != "none"]
            cached["default"] = next(iter(cached["values"]), "")
        if cached is not None:
            return cached
        name = model.removesuffix(":free").removesuffix(":nitro")
        if name.startswith("openai/"):
            return capabilities("openai", name[7:])
        if name in {"deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"}:
            return {"parameter": "reasoning.effort", "values": ["none", "high", "xhigh"], "default": "none"}
        if name in {"deepseek/deepseek-flash", "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash-1017",
                    "deepseek/deepseek-v4-flash-0731", "deepseek/deepseek-v4-flash-vision-exp"}:
            return {"parameter": "reasoning.effort", "values": ["none", "low", "high", "max"], "default": "none"}
    return {}


def project_configuration(choice, selected="", *, has_guidance=False):
    if choice.startswith("gemini-"):
        provider, model = "gemini", choice
    elif choice.startswith("api:"):
        from haizflow.services.translation_connections import resolve
        try:
            profile = resolve(choice)
        except ValueError:
            return {}
        provider, model = profile["provider"], profile["model"]
    else:
        return {}
    info = capabilities(provider, model, has_guidance=has_guidance)
    if info:
        allowed = info["values"] + (["disabled"] if info.get("thinking") else [])
        info["effective"] = selected if selected in allowed else info["default"]
    return info


def _openai_effort(model: str) -> str | None:
    # Match only documented aliases/snapshots, not future/pro/fine-tuned models.
    model = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", model.lower())
    if model in {"gpt-6-luna", "gpt-6-sol", "gpt-6.1-terra", "gpt-5.1",
                 "gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}:
        return "none"
    if model in {"gpt-6-astra", "gpt-6.1-sol", "o1", "o3", "o3-mini", "o4-mini"}:
        return "low"
    if model in {"gpt-5", "gpt-5-mini", "gpt-5-nano"}:
        return "minimal"
    return None


def request_options(provider: str, model: str, effort: str = "") -> dict:
    """Never switch models or inject vendor-specific knobs into custom APIs."""
    if effort:
        info = capabilities(provider, model)
        if not info or effort not in info["values"] + (["disabled"] if info.get("thinking") else []):
            raise ValueError("Mức reasoning không được model đang chọn hỗ trợ.")
        if provider == "openrouter" and info.get("toggle"):
            return {"reasoning": {"enabled": effort == "enabled", "exclude": True}}
        if provider == "deepseek":
            return {"thinking": {"type": "disabled"}} if effort == "disabled" else {
                "thinking": {"type": "enabled"}, "reasoning_effort": effort}
        return {"reasoning": {"effort": effort, **({"exclude": True} if provider == "openrouter" else {})}}
    if provider == "openai":
        effort = _openai_effort(model)
        return {"reasoning": {"effort": effort}} if effort else {}
    if provider == "deepseek" and model.lower() in {"deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash"}:
        return {"thinking": {"type": "disabled"}}
    if provider == "openrouter":
        info = capabilities(provider, model)
        if info.get("toggle"):
            return {"reasoning": {"enabled": False, "exclude": True}}
        if info.get("default"):
            return {"reasoning": {"effort": info["default"], "exclude": True}}
        if info.get("mandatory"):
            return {"reasoning": {"exclude": True}}  # Hide, never disable, mandatory reasoning.
        name = model.removesuffix(":free").removesuffix(":nitro")
        effort = _openai_effort(name[7:]) if name.startswith("openai/") else None
        if name in {"deepseek/deepseek-flash", "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash",
                    "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash-1017",
                    "deepseek/deepseek-v4-flash-0731", "deepseek/deepseek-v4-flash-vision-exp"}:
            effort = "none"
        if effort:
            return {"reasoning": {"effort": effort, "exclude": True}}
    return {}
