import argparse
import gc
import json
import os
import sys
from pathlib import Path


_INFERENCE_BATCH_SIZE = max(1, min(8, int(os.getenv("HYMT2_INFERENCE_BATCH_SIZE", "4"))))
_CONTEXT_SEGMENTS = 3
_MAX_CONTEXT_CHARACTERS = 1200
_GLOBAL_CONTEXT_SEGMENTS = 3
_MAX_BACKGROUND_CHARACTERS = 2400
_PROGRESS_PATH = None
_MODEL_RUNTIME = None


def _emit_event(payload: dict) -> None:
    # Keep the worker protocol ASCII-safe so Windows console code pages cannot
    # corrupt or reject translated Unicode text. json.loads restores Unicode.
    line = json.dumps(payload, ensure_ascii=True)
    if _PROGRESS_PATH is not None:
        with open(_PROGRESS_PATH, "a", encoding="utf-8") as file:
            file.write(line + "\n")
        return
    if sys.stdout is not None:
        print(line, flush=True)


def _inference_batches(texts: list[str], batch_size: int = _INFERENCE_BATCH_SIZE):
    """Yield prompt batches; each prompt still produces exactly one subtitle."""
    for start in range(0, len(texts), batch_size):
        yield start, min(len(texts), start + batch_size)


def _context_before_start(texts: list[str], core_start: int) -> int:
    start = max(0, core_start - _CONTEXT_SEGMENTS)
    while start < core_start and sum(len(text) for text in texts[start:core_start]) > _MAX_CONTEXT_CHARACTERS:
        start += 1
    return start


def _context_after_end(texts: list[str], core_end: int) -> int:
    end = min(len(texts), core_end + _CONTEXT_SEGMENTS)
    while end > core_end and sum(len(text) for text in texts[core_end:end]) > _MAX_CONTEXT_CHARACTERS:
        end -= 1
    return end


def _is_short_label(text: str) -> bool:
    source_label = text.strip().rstrip(".!?。！？").strip()
    return bool(source_label) and len(source_label) <= 40 and len(source_label.split()) <= 2


def _context_indices(texts: list[str], index: int) -> list[int]:
    """Use topic anchors and preceding subtitles without leaking future source text."""
    priority = []
    priority.extend(range(min(_GLOBAL_CONTEXT_SEGMENTS, len(texts))))
    if not _is_short_label(texts[index]):
        for distance in range(1, _CONTEXT_SEGMENTS + 1):
            priority.append(index - distance)

    selected = []
    used_characters = 0
    for context_index in priority:
        if context_index == index or context_index < 0 or context_index >= len(texts) or context_index in selected:
            continue
        item_characters = len(texts[context_index])
        if used_characters + item_characters > _MAX_BACKGROUND_CHARACTERS:
            continue
        selected.append(context_index)
        used_characters += item_characters
    return sorted(selected)


def _build_prompt(
    texts: list[str],
    source_languages: list[str],
    index: int,
    target_language_name: str,
    *,
    include_context: bool = True,
) -> str:
    context_block = ""
    if include_context:
        context_lines = []
        for context_index in _context_indices(texts, index):
            context_lines.append(f"- [{source_languages[context_index]}] {texts[context_index]}")
        context_parts = [f"Source language: {source_languages[index]}"]
        if context_lines:
            context_parts.append(
                "Video subtitle context in chronological order. It is reference only and is not text to translate:\n"
                + "\n".join(context_lines)
            )
        context_block = "[Background Information]\n" + "\n".join(context_parts) + "\n\n"

    if context_block:
        short_label_rule = ""
        if _is_short_label(texts[index]):
            short_label_rule = (
                " The [Source Text] is a standalone label: preserve its exact identity and level of specificity. "
                "If there is no certain exact equivalent, transliterate or preserve it rather than substituting "
                "a different item or a more specific subtype."
            )
        return (
            f"{context_block}Please translate only the following [Source Text] into {target_language_name}, "
            "taking the provided background information into consideration. Preserve the exact meaning and identity "
            "of names, objects, numbers, percentages, and ranking labels. The [Source Text] always takes priority over "
            f"the background; never replace its subject with a different item from the context.{short_label_rule} "
            "Note that you must ONLY output the translated "
            "result without any additional explanation or background text.\n\n"
            f"[Source Text]\n{texts[index]}"
        )
    return (
        f"Translate the following text into {target_language_name}. Note that you should only output "
        "the translated result without any additional explanation:\n\n"
        f"{texts[index]}"
    )


def _build_translation_prompts(
    texts: list[str],
    source_languages: list[str],
    start: int,
    end: int,
    target_language_name: str,
) -> list[str]:
    return [
        _build_prompt(texts, source_languages, index, target_language_name)
        for index in range(start, end)
    ]


def _clean_single_translation(response: str) -> str:
    """Accept a plain or JSON-encoded translation for the one-item fallback."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = text
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], str):
        parsed = parsed[0]
    if not isinstance(parsed, str) or not parsed.strip():
        raise ValueError("HY-MT2 did not return a usable translation for one subtitle.")
    return parsed.strip().strip('"').strip()


def _encode_prompts(tokenizer, torch, device: str, prompts: list[str]):
    rendered_prompts = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            tokenize=False,
        )
        for prompt in prompts
    ]
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    encoded = tokenizer(rendered_prompts, padding=True, return_tensors="pt")
    encoded = {name: value.to(device) for name, value in encoded.items()}
    encoded.pop("token_type_ids", None)
    return encoded


def _translate_prompt_batch(
    model,
    tokenizer,
    torch,
    device: str,
    prompts: list[str],
    source_texts: list[str],
) -> list[str]:
    encoded = _encode_prompts(tokenizer, torch, device, prompts)
    input_length = encoded["input_ids"].shape[-1]
    context_limit = getattr(model.config, "max_position_embeddings", 32768)
    available_output = context_limit - input_length
    if available_output < 64:
        raise RuntimeError("Translation context window is full before the subtitle batch can be generated.")
    longest_source_tokens = max(
        len(tokenizer.encode(text, add_special_tokens=False))
        for text in source_texts
    )
    output_budget = min(384, max(48, longest_source_tokens * 4 + 16))
    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            do_sample=True,
            temperature=0.7,
            top_p=0.6,
            top_k=20,
            repetition_penalty=1.05,
            max_new_tokens=min(output_budget, available_output),
            pad_token_id=tokenizer.pad_token_id,
        )
    if len(generated) != len(prompts):
        raise RuntimeError("HY-MT2 inference did not return one result per subtitle prompt.")
    return [
        _clean_single_translation(
            tokenizer.decode(output[input_length:], skip_special_tokens=True).strip()
        )
        for output in generated
    ]


def _load_model(model_name: str):
    # Torch's CPU loader is more stable on Windows when model deserialization
    # does not fan out across every logical processor.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    _emit_event({"event": "status", "detail": "Loading HY-MT2 tokenizer"})
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    load_options = {
        "dtype": dtype,
        "trust_remote_code": True,
    }
    _emit_event({"event": "status", "detail": "Loading HY-MT2 weights"})
    model = AutoModelForCausalLM.from_pretrained(model_name, **load_options)
    _emit_event({"event": "status", "detail": f"HY-MT2 weights loaded; moving model to {device}"})
    # Match Tencent's recommended inference parameters for the 1.8B checkpoint.
    model.generation_config.do_sample = True
    model.generation_config.temperature = 0.7
    model.generation_config.top_p = 0.6
    model.generation_config.top_k = 20
    model.to(device)
    model.eval()
    _emit_event({"event": "status", "detail": "HY-MT2 model is ready"})
    return model, tokenizer, torch, device


def _model_runtime():
    global _MODEL_RUNTIME
    if _MODEL_RUNTIME is None:
        from autodub.config import HYMT2_MODEL

        _emit_event({"event": "status", "detail": "Loading HY-MT2 translation model"})
        _MODEL_RUNTIME = _load_model(HYMT2_MODEL)
    else:
        _emit_event({"event": "status", "detail": "Reusing HY-MT2 translation model"})
    return _MODEL_RUNTIME


def release_model() -> None:
    global _MODEL_RUNTIME
    if _MODEL_RUNTIME is None:
        return
    model, tokenizer, torch, _device = _MODEL_RUNTIME
    _MODEL_RUNTIME = None
    del model, tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def translate(payload: dict) -> list[str]:
    texts = payload["texts"]
    source_languages = payload.get("source_languages")
    if not isinstance(source_languages, list) or len(source_languages) != len(texts):
        source_languages = [payload.get("source_language") or "English"] * len(texts)
    target_language_name = payload["target_language_name"]
    target_key = target_language_name.casefold().strip()
    requires_translation = [
        source_language.casefold().strip() != target_key
        for source_language in source_languages
    ]
    if not any(requires_translation):
        _emit_event({"event": "progress", "current": len(texts), "total": len(texts)})
        return list(texts)

    model, tokenizer, torch, device = _model_runtime()
    translations = [None] * len(texts)
    for batch_start, batch_end in _inference_batches(texts):
        _emit_event(
            {
                "event": "batch_started",
                "start": batch_start + 1,
                "end": batch_end,
                "completed": batch_start,
                "total": len(texts),
            }
        )
        translated_indices = [
            index
            for index in range(batch_start, batch_end)
            if requires_translation[index]
        ]
        for index in range(batch_start, batch_end):
            if not requires_translation[index]:
                translations[index] = texts[index]

        if translated_indices:
            prompts = [
                _build_prompt(texts, source_languages, index, target_language_name)
                for index in translated_indices
            ]
            batch_translations = _translate_prompt_batch(
                model,
                tokenizer,
                torch,
                device,
                prompts,
                [texts[index] for index in translated_indices],
            )
            for index, translated_text in zip(translated_indices, batch_translations):
                translations[index] = translated_text

        _emit_event({"event": "progress", "current": batch_end, "total": len(texts)})
    if any(not isinstance(text, str) for text in translations):
        raise RuntimeError("HY-MT2 inference did not return one translation per subtitle prompt.")
    return translations


def _serve() -> int:
    try:
        for raw_line in sys.stdin:
            request_id = "unknown"
            try:
                request = json.loads(raw_line)
                request_id = request["request_id"]
                if request.get("command") == "shutdown":
                    _emit_event({"event": "response", "request_id": request_id, "stopped": True})
                    return 0
                if request.get("command") == "ping":
                    _emit_event({"event": "response", "request_id": request_id, "ready": True})
                    continue
                if request.get("command") == "warm":
                    _model_runtime()
                    _emit_event({"event": "response", "request_id": request_id, "warmed": True})
                    continue
                result = {"translations": translate(request["payload"])}
            except Exception as exc:
                result = {"error": f"HY-MT2 worker failed: {type(exc).__name__}: {exc}"}
            result.update({"event": "response", "request_id": request_id})
            _emit_event(result)
    finally:
        release_model()
    return 0


def main(argv=None) -> int:
    global _PROGRESS_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--request")
    parser.add_argument("--response")
    parser.add_argument("--progress")
    parser.add_argument("--server", action="store_true")
    args = parser.parse_args(argv)
    if args.server:
        return _serve()
    if not args.request or not args.response:
        parser.error("--request and --response are required unless --server is used")
    response_path = Path(args.response)
    _PROGRESS_PATH = Path(args.progress) if args.progress else None
    if _PROGRESS_PATH is not None:
        _PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PROGRESS_PATH.write_text("", encoding="utf-8")
    try:
        with open(args.request, "r", encoding="utf-8") as file:
            payload = json.load(file)
        result = {"translations": translate(payload)}
    except Exception as exc:
        result = {"error": f"HY-MT2 worker failed: {type(exc).__name__}: {exc}"}
    with open(response_path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False)
    release_model()
    _PROGRESS_PATH = None
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
