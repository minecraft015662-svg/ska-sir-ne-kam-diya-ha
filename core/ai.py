"""Provider-agnostic AI client for the Omega hosting panel.

Only two providers are supported on purpose (the ones the panel admin can
configure): Google Gemini and xAI Grok. The panel stores the API key in its
settings table and every AI feature (web assistant, Discord /ask, prefix !ai)
calls through this module, so a single key change applies everywhere.
"""
from __future__ import annotations

import json
from typing import Iterable

import requests

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"

PROVIDERS: dict[str, dict] = {
    "gemini": {
        "label": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        # Tried in order when the configured model is not available for the key.
        "fallbacks": ["gemini-2.5-flash", "gemini-3-flash", "gemini-2.0-flash"],
        "key_url": "https://aistudio.google.com/app/apikey",
        "key_hint": "AI Studio API key (starts with AIza...)",
    },
    "grok": {
        "label": "xAI Grok",
        "default_model": "grok-4.7",
        "fallbacks": ["grok-4.7", "grok-4.6", "grok-4", "grok-3"],
        "key_url": "https://console.x.ai/",
        "key_hint": "xAI API key (starts with xai-...)",
    },
}

DEFAULT_PROVIDER = "gemini"
DEFAULT_SYSTEM_PROMPT = (
    "You are the built-in assistant of an Omega hosting panel (VPS control panel). "
    "Answer short, practical questions about the user's servers, LXC containers, "
    "KVM/non-KVM virtual machines, nesting, SSH, backups and panel settings. "
    "Never invent credentials, node names or IP addresses that are not in the supplied "
    "context. If an action needs administrator rights, say so instead of pretending it "
    "was done. Reply in the language the user writes in."
)


class AIError(RuntimeError):
    """Raised when no provider could answer. Message is safe to show to users."""


def provider_meta(provider: str | None) -> dict:
    return PROVIDERS.get(str(provider or "").strip().lower(), PROVIDERS[DEFAULT_PROVIDER])


def provider_slug(provider: str | None) -> str:
    slug = str(provider or "").strip().lower()
    return slug if slug in PROVIDERS else DEFAULT_PROVIDER


def default_model(provider: str | None) -> str:
    return provider_meta(provider)["default_model"]


def model_candidates(provider: str, model: str | None) -> list[str]:
    meta = provider_meta(provider)
    ordered: list[str] = []
    for value in [str(model or "").strip(), meta["default_model"], *meta["fallbacks"]]:
        value = value.strip()
        if value and value not in ordered:
            ordered.append(value)
    return ordered


def _clean_history(history: Iterable[dict] | None, limit: int = 12) -> list[dict]:
    cleaned: list[dict] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = "assistant" if str(item.get("role")) in {"assistant", "model", "bot"} else "user"
        content = str(item.get("content") or item.get("text") or "").strip()
        if content:
            cleaned.append({"role": role, "content": content[:6000]})
    return cleaned[-limit:]


def _gemini_call(api_key: str, model: str, system_prompt: str, messages: list[dict],
                 max_tokens: int, temperature: float, timeout: int) -> str:
    contents = [
        {"role": "model" if item["role"] == "assistant" else "user",
         "parts": [{"text": item["content"]}]}
        for item in messages
    ]
    body = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": int(max_tokens), "temperature": float(temperature)},
    }
    if system_prompt:
        body["system_instruction"] = {"parts": [{"text": system_prompt}]}
    response = requests.post(
        GEMINI_ENDPOINT.format(model=model),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise AIError(_http_error("Gemini", response))
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        feedback = (data.get("promptFeedback") or {}).get("blockReason")
        raise AIError(f"Gemini returned no answer{f' ({feedback})' if feedback else ''}.")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise AIError("Gemini returned an empty answer.")
    return text


def _grok_call(api_key: str, model: str, system_prompt: str, messages: list[dict],
               max_tokens: int, temperature: float, timeout: int) -> str:
    payload = list(messages)
    if system_prompt:
        payload = [{"role": "system", "content": system_prompt}] + payload
    response = requests.post(
        GROK_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": payload,
              "max_tokens": int(max_tokens), "temperature": float(temperature)},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise AIError(_http_error("Grok", response))
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise AIError("Grok returned no answer.")
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise AIError("Grok returned an empty answer.")
    return text


def _http_error(label: str, response: requests.Response) -> str:
    detail = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message") or error.get("status") or "")
            elif error:
                detail = str(error)
            detail = detail or str(body.get("message") or "")
    except ValueError:
        detail = (response.text or "")[:300]
    if response.status_code in (401, 403):
        return f"{label} rejected the API key (HTTP {response.status_code}). {detail}".strip()
    if response.status_code == 429:
        return f"{label} rate limit or quota reached (HTTP 429). {detail}".strip()
    return f"{label} error (HTTP {response.status_code}). {detail}".strip()


def chat(provider: str, api_key: str, model: str | None, system_prompt: str,
         message: str, history: Iterable[dict] | None = None,
         max_tokens: int = 900, temperature: float = 0.4, timeout: int = 60) -> dict:
    """Send a chat turn and return {reply, provider, model}.

    Model auto-fallback keeps the assistant working when a provider retires the
    configured model name. Auth/quota failures are reported immediately.
    """
    provider = provider_slug(provider)
    api_key = str(api_key or "").strip()
    message = str(message or "").strip()
    if not api_key:
        raise AIError(f"No {provider_meta(provider)['label']} API key is saved. Ask an administrator to add one in Admin → AI settings.")
    if not message:
        raise AIError("Message is empty.")
    if len(message) > 8000:
        message = message[:8000]

    messages = _clean_history(history) + [{"role": "user", "content": message}]
    system_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT).strip()[:8000]
    last_error: Exception | None = None
    for candidate in model_candidates(provider, model):
        try:
            if provider == "grok":
                reply = _grok_call(api_key, candidate, system_prompt, messages,
                                   max_tokens, temperature, timeout)
            else:
                reply = _gemini_call(api_key, candidate, system_prompt, messages,
                                     max_tokens, temperature, timeout)
            return {"reply": reply, "provider": provider, "model": candidate}
        except requests.RequestException as exc:
            raise AIError(f"Could not reach {provider_meta(provider)['label']}: {exc}") from exc
        except AIError as exc:
            last_error = exc
            message_text = str(exc).lower()
            retryable_model = any(token in message_text for token in ("not found", "404", "not supported", "does not exist", "invalid model", "model"))
            if retryable_model and "api key" not in message_text and "quota" not in message_text:
                continue
            raise
    raise last_error or AIError("No AI model could answer the request.")


def provider_key(settings: dict, provider: str | None = None) -> str:
    settings = dict(settings or {})
    provider = provider_slug(provider or settings.get("ai_provider"))
    column = "gemini_api_key" if provider == "gemini" else "grok_api_key"
    return str(settings.get(column) or settings.get("ai_api_key") or "").strip()


def provider_model(settings: dict, provider: str | None = None) -> str:
    settings = dict(settings or {})
    provider = provider_slug(provider or settings.get("ai_provider"))
    column = "gemini_model" if provider == "gemini" else "grok_model"
    return str(settings.get(column) or settings.get("ai_model") or "").strip() or default_model(provider)


def is_enabled(settings: dict) -> bool:
    value = dict(settings or {}).get("ai_enabled", 1)
    if value is None:
        return True
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def configured(settings: dict) -> dict:
    settings = dict(settings or {})
    provider = provider_slug(settings.get("ai_provider"))
    return {
        "enabled": is_enabled(settings),
        "provider": provider,
        "provider_label": provider_meta(provider)["label"],
        "model": provider_model(settings, provider),
        "has_key": bool(provider_key(settings, provider)),
    }


def answer_with_settings(settings: dict, prompt: str, history: Iterable[dict] | None = None,
                         context: str = "") -> dict:
    """Answer using the admin-configured key. Shared by the panel and the bot."""
    settings = dict(settings or {})
    if not is_enabled(settings):
        raise AIError("The AI assistant is disabled by the panel administrator.")
    provider = provider_slug(settings.get("ai_provider"))
    system_prompt = str(settings.get("ai_system_prompt") or DEFAULT_SYSTEM_PROMPT).strip()
    if context:
        system_prompt = f"{system_prompt}\n\n{context.strip()[:6000]}"
    try:
        max_tokens = max(120, min(4000, int(settings.get("ai_max_tokens") or 900)))
    except (TypeError, ValueError):
        max_tokens = 900
    return chat(provider, provider_key(settings, provider), provider_model(settings, provider),
                system_prompt, prompt, history=history, max_tokens=max_tokens)


def parse_json_body(raw: str | bytes | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
