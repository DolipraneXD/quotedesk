"""The Claude and Gemini extractors against stubbed SDK clients: request shape, responses."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import groq
import httpx
import pytest
from google.genai import errors as genai_errors

from app.seed import BRANDS, CATEGORIES, GENERIC_SCHEMA, SCHEMAS
from app.services.importer.extract_media import ImageInput
from app.services.importer.llm_parser import (
    ChunkContext,
    ClaudeExtractor,
    ExtractionError,
    GeminiExtractor,
    GroqExtractor,
    InceptionExtractor,
    OutputTooLong,
    output_schema,
    parse_output,
    system_prompt,
)

CODES = [c[0] for c in CATEGORIES]
GOOD = {
    "sheet_meta": {"currency": "USD", "fx_rate": None, "price_date": None},
    "rows": [{"source_row": 4, "prices": [{"amount": 14.85}]}],
}


def message(text: str = json.dumps(GOOD), stop_reason: str = "end_turn", category=None):
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=category) if category else None,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(
            input_tokens=100, cache_read_input_tokens=900, cache_creation_input_tokens=0,
            output_tokens=50,
        ),
        model="claude-sonnet-5-5",
    )  # fmt: skip


class StubStream:
    def __init__(self, msg):
        self.msg = msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self.msg


class StubClient:
    def __init__(self, messages: list[Any]):
        self.messages = list(messages)
        self.calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return StubStream(self.messages.pop(0))


def context() -> ChunkContext:
    return ChunkContext("f.xlsx", "Sheet", "wifi", "USD", Decimal("6.71"), "2026-09-29", "| row |")


def extractor(client: StubClient) -> ClaudeExtractor:
    return ClaudeExtractor(
        api_key="test", model="claude-sonnet-5-5", system="SYSTEM", category_codes=CODES,
        client=client,  # type: ignore[arg-type]
    )  # fmt: skip


def run(coro):
    return asyncio.run(coro)


def test_request_shape():
    client = StubClient([message()])
    run(extractor(client).extract(context()))
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["effort"] == "medium"
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    content = call["messages"][0]["content"]
    assert "Sheet: Sheet" in content and "Category hint for this sheet: wifi" in content
    assert "Detected exchange rate: 6.71" in content and content.endswith("| row |")


def test_success_parses_decimals_and_sums_tokens():
    result = run(extractor(StubClient([message()])).extract(context()))
    amount = result.rows[0]["prices"][0]["amount"]
    assert isinstance(amount, Decimal) and amount == Decimal("14.85")
    assert result.input_tokens == 1000 and result.output_tokens == 50


def test_invalid_json_is_retried_then_fails():
    client = StubClient([message("{not json"), message("[]"), message(json.dumps(GOOD))])
    assert run(extractor(client).extract(context())).rows
    assert len(client.calls) == 3
    client = StubClient([message("{bad")] * 3)
    with pytest.raises(ExtractionError, match="Invalid output"):
        run(extractor(client).extract(context()))


def test_refusal_and_max_tokens():
    with pytest.raises(ExtractionError, match="declined"):
        run(
            extractor(StubClient([message(stop_reason="refusal", category="cyber")])).extract(
                context()
            )
        )
    with pytest.raises(OutputTooLong):
        run(extractor(StubClient([message(stop_reason="max_tokens")])).extract(context()))


def test_parse_output_requires_rows():
    with pytest.raises(ValueError):
        parse_output('{"sheet_meta": {}}')


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def test_output_schema_is_strict():
    schema = output_schema(CODES)
    objects = [n for n in _walk(schema) if n.get("type") == "object"]
    assert objects
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    row = schema["properties"]["rows"]["items"]
    assert row["properties"]["category_code"]["enum"] == CODES


def test_system_prompt_lists_categories_schemas_and_brands():
    cats = [
        SimpleNamespace(
            code=c, name_en=en, name_zh=zh, attribute_schema=SCHEMAS.get(c, GENERIC_SCHEMA)
        )
        for c, en, zh, _ in CATEGORIES
    ]
    brands = [
        SimpleNamespace(
            canonical=canonical,
            aliases=[SimpleNamespace(alias=a) for a in [canonical, zh, *extra] if a],
        )
        for canonical, zh, extra in BRANDS
    ]
    prompt = system_prompt(cats, brands)
    assert "RIGHT-MOST" in prompt
    assert "- ram_module: RAM module / 内存条; type*, capacity_gb*, speed_mhz*" in prompt
    assert "- SK hynix: SKhynix, hynix, 海力士" in prompt
    assert "- Yemas" in prompt


# ------------------------------------------------------------------ Gemini


def gemini_response(
    text: str = json.dumps(GOOD), finish: str = "STOP", block: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_feedback=SimpleNamespace(block_reason=block) if block else None,
        candidates=[] if block else [SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
        text=None if block else text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=1000, candidates_token_count=40, thoughts_token_count=10
        ),
        model_version="gemini-3.8-flash",
    )


class StubGemini:
    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate))

    async def _generate(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def gemini(client: StubGemini) -> GeminiExtractor:
    return GeminiExtractor(
        api_key="test", model="gemini-3.8-flash", system="SYSTEM", category_codes=CODES,
        client=client,  # type: ignore[arg-type]
    )  # fmt: skip


def test_gemini_request_shape_and_result():
    client = StubGemini([gemini_response()])
    result = run(gemini(client).extract(context()))
    call = client.calls[0]
    assert call["model"] == "gemini-3.8-flash"
    assert "Sheet: Sheet" in call["contents"] and call["contents"].endswith("| row |")
    config = call["config"]
    assert config.system_instruction == "SYSTEM"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == output_schema(CODES)
    assert config.thinking_config.thinking_level.name == "MEDIUM"
    amount = result.rows[0]["prices"][0]["amount"]
    assert isinstance(amount, Decimal) and amount == Decimal("14.85")
    assert result.input_tokens == 1000 and result.output_tokens == 50  # thinking counted
    assert result.model == "gemini-3.8-flash"


def test_gemini_retries_invalid_json():
    client = StubGemini([gemini_response("{bad"), gemini_response()])
    assert run(gemini(client).extract(context())).rows
    assert len(client.calls) == 2


def test_gemini_max_tokens_blocked_and_api_errors():
    with pytest.raises(OutputTooLong):
        run(gemini(StubGemini([gemini_response(finish="MAX_TOKENS")])).extract(context()))
    with pytest.raises(ExtractionError, match="declined"):
        run(gemini(StubGemini([gemini_response(finish="SAFETY")])).extract(context()))
    with pytest.raises(ExtractionError, match="declined"):
        run(gemini(StubGemini([gemini_response(block="PROHIBITED_CONTENT")])).extract(context()))
    error = genai_errors.ClientError(429, {"error": {"message": "quota", "status": "x"}})
    with pytest.raises(ExtractionError, match="API error 429"):
        run(gemini(StubGemini([error])).extract(context()))
    with pytest.raises(ExtractionError, match="Request failed"):
        run(gemini(StubGemini([ConnectionError("down")])).extract(context()))


# ------------------------------------------------------------------ images


def image_context() -> ChunkContext:
    return ChunkContext(
        "shots", "img_cpu.jpg", "cpu", None, None, None, "", kind="image",
        images=[ImageInput("image/jpeg", b"\xff\xd8jpeg")],
    )  # fmt: skip


def test_claude_sends_images_before_the_text():
    client = StubClient([message()])
    run(extractor(client).extract(image_context()))
    call = client.calls[0]
    assert call["max_tokens"] == 64000
    image, text = call["messages"][0]["content"]
    assert image == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": "/9hqcGVn"},
    }
    assert text["type"] == "text"
    assert "Source: Screenshot (attached image)" in text["text"]
    assert text["text"].endswith("File date: unknown")  # no grid after the hints


def test_gemini_sends_images_in_high_resolution():
    client = StubGemini([gemini_response()])
    run(gemini(client).extract(image_context()))
    call = client.calls[0]
    image, text = call["contents"]
    assert image.inline_data.data == b"\xff\xd8jpeg"
    assert image.inline_data.mime_type == "image/jpeg"
    assert image.media_resolution.level.name == "MEDIA_RESOLUTION_HIGH"
    assert "Source: Screenshot" in text.text
    assert call["config"].max_output_tokens == 64000


def test_sheet_chunks_keep_the_smaller_output_cap():
    client = StubGemini([gemini_response()])
    run(gemini(client).extract(context()))
    assert client.calls[0]["config"].max_output_tokens == 32000


# -------------------------------------------------------------------- Groq


def groq_completion(text: str = json.dumps(GOOD), finish: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=3800, completion_tokens=2200),
        model="qwen/qwen3.8-27b",
    )


class StubGroq:
    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def groq_extractor(client: StubGroq) -> GroqExtractor:
    return GroqExtractor(
        api_key="test", model="qwen/qwen3.8-27b", system="SYSTEM", category_codes=CODES,
        client=client,  # type: ignore[arg-type]
    )  # fmt: skip


def test_groq_request_shape_and_result():
    client = StubGroq([groq_completion()])
    result = run(groq_extractor(client).extract(image_context()))
    call = client.calls[0]
    assert call["model"] == "qwen/qwen3.8-27b"
    assert call["messages"][0] == {"role": "system", "content": "SYSTEM"}
    text, image = call["messages"][1]["content"]
    assert text["type"] == "text" and "Source: Screenshot" in text["text"]
    assert image == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9hqcGVn"}}
    fmt = call["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == output_schema(CODES)
    assert call["max_completion_tokens"] == 16384  # Groq's cap, below the 64K media cap
    assert call["reasoning_format"] == "hidden"
    amount = result.rows[0]["prices"][0]["amount"]
    assert isinstance(amount, Decimal) and amount == Decimal("14.85")
    assert (result.input_tokens, result.output_tokens) == (3800, 2200)


def test_groq_length_retry_and_errors():
    with pytest.raises(OutputTooLong):
        run(groq_extractor(StubGroq([groq_completion(finish="length")])).extract(context()))
    client = StubGroq([groq_completion("{bad"), groq_completion()])
    assert run(groq_extractor(client).extract(context())).rows
    assert len(client.calls) == 2
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"))
    error = groq.RateLimitError("Rate limit reached", response=response, body=None)
    with pytest.raises(ExtractionError, match="API error 429"):
        run(groq_extractor(StubGroq([error])).extract(context()))


# -------------------------------------------------------------------- Inception


def inception_body(text: str = json.dumps(GOOD), finish: str = "stop") -> dict[str, Any]:
    return {
        "model": "mercury-2.5",
        "choices": [{"finish_reason": finish, "message": {"content": text}}],
        "usage": {"prompt_tokens": 3800, "completion_tokens": 2200},
    }


def inception(responses: list[httpx.Response]) -> tuple[InceptionExtractor, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses.pop(0)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    extractor = InceptionExtractor(
        api_key="sk_test", model="mercury-2.5", system="SYSTEM", category_codes=CODES,
        client=client,
    )  # fmt: skip
    return extractor, calls


def test_inception_request_shape_and_result():
    extractor, calls = inception([httpx.Response(200, json=inception_body())])
    result = run(extractor.extract(context()))
    request = calls[0]
    assert str(request.url) == "https://api.inceptionlabs.ai/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk_test"
    call = json.loads(request.content)
    assert call["model"] == "mercury-2.5" and call["reasoning_effort"] == "medium"
    assert call["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert call["messages"][1]["content"].endswith("| row |")
    fmt = call["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == output_schema(CODES)
    assert call["max_tokens"] == 32000
    amount = result.rows[0]["prices"][0]["amount"]
    assert isinstance(amount, Decimal) and amount == Decimal("14.85")
    assert (result.input_tokens, result.output_tokens) == (3800, 2200)


def test_inception_is_text_only():
    extractor, calls = inception([httpx.Response(200, json=inception_body())])
    with pytest.raises(ExtractionError, match="text only"):
        run(extractor.extract(image_context()))
    page = ChunkContext(
        "q.pdf", "Page 1", None, None, None, None, "1: CPU 100", kind="pdf_page",
        images=[ImageInput("image/jpeg", b"\xff\xd8jpeg")],
    )  # fmt: skip
    run(extractor.extract(page))
    content = json.loads(calls[0].content)["messages"][1]["content"]
    assert isinstance(content, str) and "1: CPU 100" in content and "not attached" in content


def test_inception_length_retry_and_errors(monkeypatch):
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    extractor, _ = inception([httpx.Response(200, json=inception_body(finish="length"))])
    with pytest.raises(OutputTooLong):
        run(extractor.extract(context()))
    bad, good = inception_body("{bad"), inception_body()
    extractor, calls = inception([httpx.Response(200, json=bad), httpx.Response(200, json=good)])
    assert run(extractor.extract(context())).rows and len(calls) == 2
    busy = httpx.Response(429, json={"error": {"message": "Rate limit reached"}})
    extractor, calls = inception([busy, httpx.Response(200, json=inception_body())])
    assert run(extractor.extract(context())).rows and len(calls) == 2  # retried
    denied = httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})
    extractor, _ = inception([denied])
    with pytest.raises(ExtractionError, match="API error 401: Incorrect API key"):
        run(extractor.extract(context()))
