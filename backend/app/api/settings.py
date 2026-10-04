from __future__ import annotations

from typing import Any

import anthropic
import groq
from fastapi import APIRouter
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel

from app.config import (
    AppSettings,
    active_model,
    get_api_key,
    load_settings,
    save_settings,
    set_api_key,
)
from app.errors import ProblemError

router = APIRouter(tags=["settings"])


class SettingsOut(AppSettings):
    anthropic_api_key_set: bool = False
    gemini_api_key_set: bool = False
    groq_api_key_set: bool = False


class SettingsIn(AppSettings):
    # None = leave unchanged, "" = remove the stored key
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    groq_api_key: str | None = None


def _out() -> SettingsOut:
    return SettingsOut(
        **load_settings().model_dump(),
        anthropic_api_key_set=bool(get_api_key("anthropic")),
        gemini_api_key_set=bool(get_api_key("google")),
        groq_api_key_set=bool(get_api_key("groq")),
    )


@router.get("/settings", response_model=SettingsOut)
def get_settings() -> SettingsOut:
    return _out()


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn) -> SettingsOut:
    data: dict[str, Any] = body.model_dump(
        exclude={"anthropic_api_key", "gemini_api_key", "groq_api_key"}
    )
    save_settings(AppSettings.model_validate(data))
    if body.anthropic_api_key is not None:
        set_api_key(body.anthropic_api_key.strip() or None, "anthropic")
    if body.gemini_api_key is not None:
        set_api_key(body.gemini_api_key.strip() or None, "google")
    if body.groq_api_key is not None:
        set_api_key(body.groq_api_key.strip() or None, "groq")
    return _out()


class LanguageIn(BaseModel):
    ui_language: str


@router.put("/settings/language", response_model=SettingsOut)
def put_language(body: LanguageIn) -> SettingsOut:
    """Persist the top-bar language switch without resending the whole settings doc."""
    settings = load_settings()
    settings.ui_language = "en" if body.ui_language == "en" else "zh"
    save_settings(settings)
    return _out()


class LlmTestOut(BaseModel):
    ok: bool
    model: str
    detail: str


PING = "Reply with the single word OK."


@router.post("/settings/test-llm", response_model=LlmTestOut)
def test_llm() -> LlmTestOut:
    """One tiny request with the saved provider, key and model, so the seller knows imports work."""
    settings = load_settings()
    key = get_api_key(settings.llm_provider)
    if not key:
        raise ProblemError(
            409, "import.no_api_key", "Set the AI provider's API key first",
            provider=settings.llm_provider,
        )  # fmt: skip
    model = active_model(settings)
    if settings.llm_provider == "google":
        return _test_gemini(key, model)
    if settings.llm_provider == "groq":
        return _test_groq(key, model)
    return _test_anthropic(key, model)


def _test_anthropic(key: str, model: str) -> LlmTestOut:
    client = anthropic.Anthropic(api_key=key, max_retries=1, timeout=30.0)
    try:
        message = client.messages.create(
            model=model, max_tokens=64, messages=[{"role": "user", "content": PING}]
        )
    except anthropic.AuthenticationError:
        return LlmTestOut(ok=False, model=model, detail="auth")
    except anthropic.NotFoundError:
        return LlmTestOut(ok=False, model=model, detail="model_not_found")
    except anthropic.APIStatusError as exc:
        return LlmTestOut(ok=False, model=model, detail=f"http_{exc.status_code}")
    except anthropic.APIConnectionError:
        return LlmTestOut(ok=False, model=model, detail="network")
    return LlmTestOut(ok=True, model=message.model, detail="ok")


def _test_gemini(key: str, model: str) -> LlmTestOut:
    client = genai.Client(api_key=key, http_options=genai_types.HttpOptions(timeout=30_000))
    try:
        response = client.models.generate_content(
            model=model,
            contents=PING,
            config=genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(
                    thinking_level=genai_types.ThinkingLevel.LOW
                )
            ),
        )
    except genai_errors.APIError as exc:
        # an invalid key is a 400 INVALID_ARGUMENT whose details name API_KEY_INVALID
        if exc.code in (401, 403) or "API_KEY_INVALID" in str(exc.details):
            return LlmTestOut(ok=False, model=model, detail="auth")
        if exc.code == 404:
            return LlmTestOut(ok=False, model=model, detail="model_not_found")
        return LlmTestOut(ok=False, model=model, detail=f"http_{exc.code}")
    except Exception:  # transport errors come from httpx, httpx2 or aiohttp
        return LlmTestOut(ok=False, model=model, detail="network")
    return LlmTestOut(ok=True, model=response.model_version or model, detail="ok")


def _test_groq(key: str, model: str) -> LlmTestOut:
    client = groq.Groq(api_key=key, max_retries=1, timeout=30.0)
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PING}],
            max_completion_tokens=64,
            reasoning_effort="none",
        )
    except groq.AuthenticationError:
        return LlmTestOut(ok=False, model=model, detail="auth")
    except groq.NotFoundError:
        return LlmTestOut(ok=False, model=model, detail="model_not_found")
    except groq.APIStatusError as exc:
        return LlmTestOut(ok=False, model=model, detail=f"http_{exc.status_code}")
    except groq.APIConnectionError:
        return LlmTestOut(ok=False, model=model, detail="network")
    return LlmTestOut(ok=True, model=completion.model or model, detail="ok")
