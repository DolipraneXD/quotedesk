"""AI extraction of product rows from price lists (plan §4.1 step 4).

Four providers share the prompt and the output schema: Claude (``ClaudeExtractor``),
Google Gemini (``GeminiExtractor``), Groq (``GroqExtractor``) and Inception Mercury
(``InceptionExtractor``, text only); Settings picks one. The
model gets a stable system prompt (rules, category schemas, brand list - cached where the
provider supports it) and one unit of work: a spreadsheet chunk rendered as a Markdown grid
with row numbers, a screenshot, or a PDF page (numbered text lines plus the rendered page).
Output is constrained with a JSON schema (structured outputs), so every response parses.
Decimal amounts are parsed with ``parse_float=Decimal``: no price ever becomes a float.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol

import anthropic
import groq
import httpx
from anthropic.types.beta import BetaOutputConfigParam
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.services.importer.extract_media import ImageInput

NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}
NULLABLE_INT = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
NULLABLE_CURRENCY = {"anyOf": [{"type": "string", "enum": ["USD", "CNY"]}, {"type": "null"}]}

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 32000  # a 60-row spreadsheet chunk
MEDIA_MAX_TOKENS = 64000  # a whole screenshot or page cannot be split; the CPU list has ~90 rows

SourceKind = Literal["sheet", "image", "pdf_page"]


class ExtractionError(Exception):
    """A chunk could not be extracted (refusal, repeated invalid output, API error)."""


class OutputTooLong(ExtractionError):
    """The model hit max_tokens; the caller should split the chunk and retry."""


@dataclass
class ChunkContext:
    filename: str
    sheet: str
    category_hint: str | None
    detected_currency: str | None
    detected_fx_rate: Decimal | None
    file_date: str | None
    body: str  # Markdown grid, numbered PDF lines, or "" for a screenshot
    kind: SourceKind = "sheet"
    images: list[ImageInput] = field(default_factory=list)

    @property
    def max_tokens(self) -> int:
        return MAX_TOKENS if self.kind == "sheet" else MEDIA_MAX_TOKENS


@dataclass
class ChunkResult:
    rows: list[dict[str, Any]]
    sheet_meta: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None
    issues: list[str] = field(default_factory=list)


class Extractor(Protocol):
    model: str

    async def extract(self, context: ChunkContext) -> ChunkResult: ...


def output_schema(category_codes: Sequence[str]) -> dict[str, Any]:
    price = {
        "type": "object",
        "properties": {
            "tier": {"type": "string", "enum": ["standard", "forecast"]},
            "amount": {"type": "number"},
            "currency": {"type": "string", "enum": ["USD", "CNY"]},
            "column": {"type": "string"},
            "date": NULLABLE_STRING,
            "original_amount": NULLABLE_NUMBER,
            "original_currency": NULLABLE_CURRENCY,
            "fx_rate": NULLABLE_NUMBER,
        },
        "required": [
            "tier", "amount", "currency", "column", "date",
            "original_amount", "original_currency", "fx_rate",
        ],
        "additionalProperties": False,
    }  # fmt: skip
    part = {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "spec": {"type": "string"},
            "category_code": {"type": "string", "enum": list(category_codes)},
            "amount": NULLABLE_NUMBER,
            "generic": {"type": "boolean"},
        },
        "required": ["label", "spec", "category_code", "amount", "generic"],
        "additionalProperties": False,
    }
    row = {
        "type": "object",
        "properties": {
            "source_row": {"type": "integer"},
            "category_code": {"type": "string", "enum": list(category_codes)},
            "name_zh": {"type": "string"},
            "name_en": NULLABLE_STRING,
            "brand": NULLABLE_STRING,
            "erp_codes": {"type": "array", "items": {"type": "string"}},
            "mpn": NULLABLE_STRING,
            "attributes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                    "required": ["key", "value"],
                    "additionalProperties": False,
                },
            },
            "prices": {"type": "array", "items": price},
            "no_price_reason": NULLABLE_STRING,
            "stock_qty": NULLABLE_INT,
            "demand_qty": NULLABLE_INT,
            "stock_after_qty": NULLABLE_INT,
            "notes_raw": NULLABLE_STRING,
            "platform": NULLABLE_STRING,
            "parts": {"type": "array", "items": part},
            "confidence": {"type": "number"},
            "issues": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "source_row", "category_code", "name_zh", "name_en", "brand", "erp_codes", "mpn",
            "attributes", "prices", "no_price_reason", "stock_qty", "demand_qty",
            "stock_after_qty", "notes_raw", "platform", "parts", "confidence", "issues",
        ],
        "additionalProperties": False,
    }  # fmt: skip
    return {
        "type": "object",
        "properties": {
            "sheet_meta": {
                "type": "object",
                "properties": {
                    "currency": NULLABLE_CURRENCY,
                    "fx_rate": NULLABLE_NUMBER,
                    "price_date": NULLABLE_STRING,
                },
                "required": ["currency", "fx_rate", "price_date"],
                "additionalProperties": False,
            },
            "rows": {"type": "array", "items": row},
        },
        "required": ["sheet_meta", "rows"],
        "additionalProperties": False,
    }  # fmt: skip


RULES = """\
You extract product price rows from supplier price lists for a hardware trading company in
Shenzhen. The lists are Excel sheets written by different colleagues, mostly in Chinese, with
no fixed layout; some arrive as screenshots of those sheets or as PDF quotations.

Spreadsheets: you receive one chunk of one sheet as a Markdown grid. The first column is the
sheet row number; the other columns are labelled "<column letter>: <header text>". Merged
cells have already been filled down, so a value repeated from the row above is a group label
(for example a type, interface or chip family that applies to every row in the group).

Screenshots: you receive the image of a table. There are no row numbers: source_row is the
position of the product row in the table, 1 for the first row under the header, counting
every product row once even when its cells wrap onto several text lines. A cell spanning
several rows (merged) applies to every row it spans. Red text is still part of the cell.

PDF pages: you receive the page text line by line, each line prefixed "L<number> |", laid
out as on the page, plus the rendered page. Use the text for exact values and the image for
the table structure (wrapped cells continue on the next lines). source_row is the number of
the line that holds the row's price. In a quotation or offer, the unit price column (Unit
price, Units Price, 单价) is the price; ignore quantities, line totals and grand totals. Put
the description text verbatim in an attribute "description". When the name is generic
(for example "Battery cabinet"), take the model from the description (for example "C6"), so
two different products never share the same model.

A note above or below a table that applies to the whole table is not a row: mention it once,
in the issues of the first row you return.

Return one output row for every product row in the chunk. Skip blank rows, section titles,
subtotals, repeated header rows and rows that only hold a remark. Set source_row to the row
number from the first column.

Prices
- The current price is the RIGHT-MOST price column that is labelled as a price (dated or
  month/week labels such as 9月价格, 参考价9/19, WK13, 9/28参考价, 报价, 价格, TTL). Columns to its
  left are history: ignore them. Unnamed repeated 参考价 columns are chronological, left to right.
- If that right-most price cell is "-", "/", 现询, 无价格, 停产, 无货无供应, 0 or empty, the row has
  no price: return an empty prices list and copy the cell text into no_price_reason. Do not
  fall back to an older column.
- Two price tiers in one sheet: 不报数 (no forecast) is tier "standard", 报数 (with forecast) is
  tier "forecast". Otherwise every price is tier "standard".
- If the sheet has a price in RMB and also a computed USD price column (often next to an
  汇率 column), report the USD column as amount/currency "USD" and put the RMB value in
  original_amount with original_currency "CNY" and the rate in fx_rate. The USD column may
  exclude VAT; never recompute it.
- If only an RMB price exists, report it as currency "CNY" with fx_rate from the row, the title
  rows or the detected sheet rate (null if none). Otherwise currency is "USD" (币种:USD, $, 美金).
- Copy amounts exactly as written; never round or convert them yourself.
- column is the column letter the price came from. date is the date the price column refers to
  (YYYY-MM-DD, year from the file date when the label has none) or null.

Identity
- erp_codes: ERP part numbers (ERP料号, 料号, IP3料号, PN; they look like E.M.W.0000119 or
  A.F.D.2400329). Split cells holding several codes on "/". "/", "-" or empty means none.
  Never invent a code.
- mpn: the manufacturer part number (原厂料号, 型号 when it is a part number), or null.
- name_zh: a short display name built from the row, keeping the source wording verbatim
  (for example "DDR4 8GB 2666MHZ 沃存 海力士颗粒 SO-DIMM"). name_en: a concise English
  translation of the same name.
- brand: the maker of the product (品牌). If it matches a brand in the list below, output that
  brand's canonical name; otherwise output it as written.
- category_code: one of the listed categories. The user's hint for the sheet is usually right,
  but choose per row.
- attributes: use the attribute keys of the chosen category (listed below) for values present
  in the row, keeping the source text and units ("8GB", "2666MHZ", "PCIE4.0"). Add other useful
  columns with short snake_case keys. Leave out empty values.

Other fields
- stock_qty (总库存), demand_qty (总实单需求), stock_after_qty (实单后库存, may be negative):
  integers or null.
- notes_raw: the remark column (备注) verbatim, or null. platform: 使用平台 / 适配平台 or null.
- Motherboard cost sheets (机型, SKU, PCB, Others, SMT, TTL): one product per 机型 + SKU row,
  category "motherboard", price = TTL, and the PCB / Others / SMT / TTL amounts as attributes
  cost_pcb, cost_others, cost_smt, cost_ttl.
- Complete-unit cost sheets (整机成本 BOMs): one row per finished product (for example a
  tablet) with its 整机成本 and USD price, followed by one column per part (屏, TP, 摄像头, 电池,
  壳料, 喇叭, 适配器, 线材, 包装, 其他, PCBA, 存储 ...), each with its spec text and its own
  amount. Return the finished product as one row: its category (tablet, laptop, pc,
  mini_pc, nas, workstation, server, smart_ring or health_tracker for a finished device),
  model = 项目名称, price = 整机成本 with its USD column as usual, and the specs as attributes.
  List EVERY part column in that row's parts, left to right: label = the column header,
  spec = the spec text, amount = the part's amount exactly as written (null for "/", "-" or
  empty), category_code = the part's category (屏 display, 摄像头 camera, 电池 battery, 壳料
  case, 适配器 adapter, 线材 cable, PCBA motherboard, 存储 emmc, 组装费 service; other when
  nothing fits), generic = true when the spec alone does not identify a specific part
  (整套, 预估, 组装费, 运费, 资源料). Do not return the parts as rows of their own. Rows of
  ordinary price lists have an empty parts list.
- confidence: 0 to 1, how sure you are the row is extracted correctly. issues: short notes on
  anything ambiguous (for example "two price columns, took the right-most").

sheet_meta: the currency most prices in the chunk use, the sheet's exchange rate (汇率) if
stated, and the date of the current price column if it is a single date (else null).
"""


def system_prompt(categories: Sequence[Any], brands: Sequence[Any]) -> str:
    lines = [RULES, "Categories (code: names; attribute keys, * = identifying):"]
    for c in categories:
        keys = ", ".join(
            f"{f['key']}{'*' if f.get('in_fingerprint') else ''}" for f in c.attribute_schema
        )
        lines.append(f"- {c.code}: {c.name_en} / {c.name_zh}; {keys}")
    lines.append("")
    lines.append("Brands (canonical name: other names):")
    for b in brands:
        others = sorted({a.alias for a in b.aliases} - {b.canonical})
        lines.append(f"- {b.canonical}: {', '.join(others)}" if others else f"- {b.canonical}")
    return "\n".join(lines)


SOURCE_LABELS = {
    "sheet": "Spreadsheet chunk",
    "image": "Screenshot (attached image)",
    "pdf_page": "PDF page (numbered text below, rendered page attached)",
}


def user_message(ctx: ChunkContext) -> str:
    hints = [
        f"File: {ctx.filename}",
        f"Source: {SOURCE_LABELS[ctx.kind]}",
        f"Sheet: {ctx.sheet}",
        f"Category hint for this sheet: {ctx.category_hint or 'none'}",
        f"Detected currency: {ctx.detected_currency or 'unknown'}",
        f"Detected exchange rate: {ctx.detected_fx_rate or 'unknown'}",
        f"File date: {ctx.file_date or 'unknown'}",
    ]
    head = "\n".join(hints)
    return f"{head}\n\n{ctx.body}" if ctx.body else head


def claude_content(ctx: ChunkContext) -> str | list[dict[str, Any]]:
    if not ctx.images:
        return user_message(ctx)
    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.media_type,
                "data": base64.standard_b64encode(image.data).decode("ascii"),
            },
        }
        for image in ctx.images
    ]
    blocks.append({"type": "text", "text": user_message(ctx)})
    return blocks


def gemini_contents(ctx: ChunkContext) -> str | list[Any]:
    if not ctx.images:
        return user_message(ctx)
    parts: list[Any] = [
        genai_types.Part.from_bytes(
            data=image.data,
            mime_type=image.media_type,
            # dense tables of small digits need the full resolution
            media_resolution=genai_types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
        )
        for image in ctx.images
    ]
    parts.append(genai_types.Part.from_text(text=user_message(ctx)))
    return parts


def parse_output(text: str) -> dict[str, Any]:
    data = json.loads(text, parse_float=Decimal)
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("output has no rows list")
    return data


class ClaudeExtractor:
    """Calls the Messages API. One instance is shared by all chunks of an import."""

    def __init__(
        self,
        api_key: str,
        model: str,
        system: str,
        category_codes: Sequence[str],
        effort: str = "medium",
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.model = model
        self.client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=4)
        self.system = system
        self.schema = output_schema(category_codes)
        self.effort = effort

    async def extract(self, context: ChunkContext) -> ChunkResult:
        last_error: Exception | None = None
        output_config: BetaOutputConfigParam = {
            "effort": self.effort,  # type: ignore[typeddict-item]
            "format": {"type": "json_schema", "schema": self.schema},
        }
        for _attempt in range(3):
            try:
                async with self.client.beta.messages.stream(
                    model=self.model,
                    max_tokens=context.max_tokens,
                    # stable prefix (rules, categories, brands) is cached across chunks
                    system=[
                        {
                            "type": "text",
                            "text": self.system,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": claude_content(context)}],  # type: ignore[typeddict-item]
                    output_config=output_config,
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                ) as stream:
                    message = await stream.get_final_message()
            except anthropic.APIStatusError as exc:
                raise ExtractionError(f"API error {exc.status_code}: {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                raise ExtractionError(f"Network error: {exc}") from exc

            if message.stop_reason == "refusal":
                category = message.stop_details.category if message.stop_details else None
                raise ExtractionError(f"The model declined this chunk ({category})")
            if message.stop_reason == "max_tokens":
                raise OutputTooLong("output exceeded max_tokens")
            text = next((b.text for b in message.content if b.type == "text"), "")
            try:
                data = parse_output(text)
            except ValueError as exc:  # json.JSONDecodeError is a ValueError
                last_error = exc
                continue
            usage = message.usage
            return ChunkResult(
                rows=data["rows"],
                sheet_meta=data.get("sheet_meta") or {},
                input_tokens=(usage.input_tokens or 0)
                + (usage.cache_read_input_tokens or 0)
                + (usage.cache_creation_input_tokens or 0),
                output_tokens=usage.output_tokens or 0,
                model=message.model,
            )
        raise ExtractionError(f"Invalid output after 3 attempts: {last_error}")


# Gemini finish reasons that mean the model would not answer this content
GEMINI_BLOCKED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE"}


class GeminiExtractor:
    """Calls the Gemini API (generateContent) with the same prompt and JSON schema.

    Gemini caches repeated prompt prefixes implicitly, so the system prompt needs no
    cache marker. Thinking tokens are billed as output and counted as such.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        system: str,
        category_codes: Sequence[str],
        client: genai.Client | None = None,
    ) -> None:
        self.model = model
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(
                timeout=600_000,  # ms; long sheets take minutes
                retry_options=genai_types.HttpRetryOptions(attempts=4),
            ),
        )
        self.config = genai_types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=output_schema(category_codes),
            thinking_config=genai_types.ThinkingConfig(
                thinking_level=genai_types.ThinkingLevel.MEDIUM
            ),
        )

    async def extract(self, context: ChunkContext) -> ChunkResult:
        last_error: Exception | None = None
        for _attempt in range(3):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=gemini_contents(context),
                    config=self.config.model_copy(update={"max_output_tokens": context.max_tokens}),
                )
            except genai_errors.APIError as exc:
                raise ExtractionError(f"API error {exc.code}: {exc.message}") from exc
            except Exception as exc:  # transport errors come from httpx, httpx2 or aiohttp
                raise ExtractionError(f"Request failed: {exc}") from exc

            feedback = response.prompt_feedback
            if feedback and feedback.block_reason:
                raise ExtractionError(f"The model declined this chunk ({feedback.block_reason})")
            candidate = response.candidates[0] if response.candidates else None
            reason = candidate.finish_reason.name if candidate and candidate.finish_reason else ""
            if reason == "MAX_TOKENS":
                raise OutputTooLong("output exceeded max_output_tokens")
            if reason in GEMINI_BLOCKED:
                raise ExtractionError(f"The model declined this chunk ({reason})")
            try:
                data = parse_output(response.text or "")
            except ValueError as exc:
                last_error = exc
                continue
            usage = response.usage_metadata
            return ChunkResult(
                rows=data["rows"],
                sheet_meta=data.get("sheet_meta") or {},
                input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=(
                    (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                    if usage
                    else 0
                ),
                model=response.model_version or self.model,
            )
        raise ExtractionError(f"Invalid output after 3 attempts: {last_error}")


# Groq caps the answer of its vision model (qwen3.8-27b) at 16K tokens
GROQ_MAX_OUTPUT = 16384


def groq_content(ctx: ChunkContext) -> str | list[dict[str, Any]]:
    if not ctx.images:
        return user_message(ctx)
    parts: list[dict[str, Any]] = [{"type": "text", "text": user_message(ctx)}]
    for image in ctx.images:
        data = base64.standard_b64encode(image.data).decode("ascii")
        parts.append(
            {"type": "image_url", "image_url": {"url": f"data:{image.media_type};base64,{data}"}}
        )
    return parts


class GroqExtractor:
    """Calls Groq's OpenAI-style chat completions with a strict JSON schema.

    Strict mode constrains decoding to the schema, so every answer parses. Groq has no
    prompt cache marker; the system prompt is simply resent. Reasoning is kept low and
    hidden: it counts against the 16K output cap that the rows need.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        system: str,
        category_codes: Sequence[str],
        client: groq.AsyncGroq | None = None,
    ) -> None:
        self.model = model
        self.client = client or groq.AsyncGroq(api_key=api_key, max_retries=4, timeout=600.0)
        self.system = system
        self.response_format: Any = {
            "type": "json_schema",
            "json_schema": {
                "name": "price_rows",
                "strict": True,
                "schema": output_schema(category_codes),
            },
        }

    async def extract(self, context: ChunkContext) -> ChunkResult:
        last_error: Exception | None = None
        messages: list[Any] = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": groq_content(context)},
        ]
        for _attempt in range(3):
            try:
                completion = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=self.response_format,
                    max_completion_tokens=min(context.max_tokens, GROQ_MAX_OUTPUT),
                    reasoning_effort="low",
                    reasoning_format="hidden",
                )
            except groq.APIStatusError as exc:
                raise ExtractionError(f"API error {exc.status_code}: {exc.message}") from exc
            except groq.APIConnectionError as exc:
                raise ExtractionError(f"Network error: {exc}") from exc

            choice = completion.choices[0]
            if choice.finish_reason == "length":
                raise OutputTooLong("output exceeded max_completion_tokens")
            try:
                data = parse_output(choice.message.content or "")
            except ValueError as exc:
                last_error = exc
                continue
            usage = completion.usage
            return ChunkResult(
                rows=data["rows"],
                sheet_meta=data.get("sheet_meta") or {},
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                model=completion.model or self.model,
            )
        raise ExtractionError(f"Invalid output after 3 attempts: {last_error}")


INCEPTION_URL = "https://api.inceptionlabs.ai/v1/chat/completions"
INCEPTION_RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}
TEXT_ONLY_PAGE = "(The rendered page is not attached: read the numbered text lines only.)"


class InceptionExtractor:
    """Calls Inception's OpenAI-style chat completions (Mercury) with a strict JSON schema.

    Mercury reads text only: spreadsheet chunks and the text layer of PDF pages work, while
    screenshots and scanned pages are refused with an error that names the other providers.
    There is no official SDK, so requests go through httpx with the SDKs' retry policy.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        system: str,
        category_codes: Sequence[str],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.client = client  # None: one short-lived client per request, closed in its loop
        self.system = system
        self.response_format: Any = {
            "type": "json_schema",
            "json_schema": {
                "name": "price_rows",
                "strict": True,
                "schema": output_schema(category_codes),
            },
        }

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.client is not None:
            return await self._send(self.client, payload)
        async with httpx.AsyncClient(timeout=600.0) as client:
            return await self._send(client, payload)

    async def _send(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(5):
            try:
                response = await client.post(INCEPTION_URL, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                if attempt == 4:
                    raise ExtractionError(f"Network error: {exc}") from exc
            else:
                if response.status_code not in INCEPTION_RETRY_STATUS or attempt == 4:
                    break
            await asyncio.sleep(2**attempt)
        if response.status_code >= 400:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.text
            raise ExtractionError(f"API error {response.status_code}: {message}")
        result: dict[str, Any] = response.json()
        return result

    async def extract(self, context: ChunkContext) -> ChunkResult:
        if context.kind != "sheet" and not context.body:
            raise ExtractionError(
                "Inception Mercury reads text only: use Claude, Gemini or Groq for "
                "screenshots and scanned PDF pages"
            )
        content = user_message(context)
        if context.kind == "pdf_page":
            content = f"{content}\n\n{TEXT_ONLY_PAGE}"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": content},
            ],
            "response_format": self.response_format,
            "max_tokens": context.max_tokens,
            "reasoning_effort": "medium",  # "low" misreads USD columns as CNY
        }
        last_error: Exception | None = None
        for _attempt in range(3):
            completion = await self._post(payload)
            choice = completion["choices"][0]
            if choice.get("finish_reason") == "length":
                raise OutputTooLong("output exceeded max_tokens")
            try:
                data = parse_output(choice["message"].get("content") or "")
            except ValueError as exc:
                last_error = exc
                continue
            usage = completion.get("usage") or {}
            return ChunkResult(
                rows=data["rows"],
                sheet_meta=data.get("sheet_meta") or {},
                input_tokens=usage.get("prompt_tokens") or 0,
                output_tokens=usage.get("completion_tokens") or 0,
                model=completion.get("model") or self.model,
            )
        raise ExtractionError(f"Invalid output after 3 attempts: {last_error}")
