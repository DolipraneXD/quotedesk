"""Value normalization and the product fingerprint (plan §3.4).

Everything here is pure: no database, no I/O. Brand resolution is injected as a
callable so the fingerprint can be computed and tested without a session.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

BrandResolver = Callable[[str], str | None]

_FULLWIDTH_EXTRA = {
    "　": " ",  # ideographic space
    "、": ",",
    "。": ".",
    "【": "[",
    "】": "]",
    "「": '"',
    "」": '"',
}


def to_halfwidth(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:  # full-width ASCII block maps 1:1 to ASCII
            out.append(chr(code - 0xFEE0))
        else:
            out.append(_FULLWIDTH_EXTRA.get(ch, ch))
    return "".join(out)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = to_halfwidth(str(value)).lower().strip()
    return re.sub(r"\s+", " ", text)


def _decimal_str(value: Decimal) -> str:
    """Canonical decimal text: no exponent, no trailing zeros (8.0 -> '8')."""
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


_NUM = r"(\d+(?:\.\d+)?)"
_CAPACITY_RE = re.compile(_NUM + r"\s*(tb|t|gb|g|mb|m)?(?![a-z])")
_CAPACITY_FACTOR = {
    None: Decimal(1),
    "g": Decimal(1),
    "gb": Decimal(1),
    "t": Decimal(1024),
    "tb": Decimal(1024),
    "m": Decimal(1) / Decimal(1024),
    "mb": Decimal(1) / Decimal(1024),
}


def normalize_capacity(value: Any) -> str:
    """Capacity in GB: '8GB' / '8 G' -> '8', '1T' -> '1024', '512M' -> '0.5'."""
    if value is None or value == "":
        return ""
    if isinstance(value, int | Decimal):
        return _decimal_str(Decimal(value))
    if isinstance(value, float):
        return _decimal_str(Decimal(str(value)))
    text = normalize_text(value)
    match = _CAPACITY_RE.search(text)
    if not match:
        return text
    number = Decimal(match.group(1)) * _CAPACITY_FACTOR[match.group(2)]
    return _decimal_str(number)


_FREQ_RE = re.compile(_NUM + r"\s*(ghz|mhz|mt/s|mts)?")


def normalize_frequency(value: Any) -> str:
    """Frequency in MHz: '2666MHZ' / '2666 MHz' / 2666 -> '2666'; '3.2GHz' -> '3200'."""
    if value is None or value == "":
        return ""
    text = normalize_text(value)
    match = _FREQ_RE.search(text)
    if not match:
        return text
    number = Decimal(match.group(1))
    if match.group(2) == "ghz":
        number *= 1000
    return _decimal_str(number)


def normalize_form_factor(value: Any) -> str:
    """'SO DIMM' / 'SODIMM' / 'SO-DIMM' -> 'sodimm'; 'SO/U DIMM' -> 'so_u_dimm'."""
    text = re.sub(r"[\s\-_]", "", normalize_text(value))
    if not text:
        return ""
    if re.fullmatch(r"(so/u|u/so)(dimm)?|so-?u", text):
        return "so_u_dimm"
    if text in ("sodimm", "so"):
        return "sodimm"
    if text in ("udimm", "u", "dimm"):
        return "udimm"
    return text


_PCIE_RE = re.compile(r"pcie?(?:gen)?(\d)(?:\.\d)?(?:x(\d+))?")


def normalize_interface(value: Any) -> str:
    """'PCIE3.0' / 'PCIe 3.0' / 'PCIE3' / 'PCIe Gen3' -> 'pcie3'."""
    text = re.sub(r"\s+", "", normalize_text(value))
    if not text:
        return ""
    match = _PCIE_RE.fullmatch(text)
    if match:
        return f"pcie{match.group(1)}"
    if text.startswith("sata"):
        return "sata"
    return text


_NUMBER_WITH_UNIT_RE = re.compile(
    r"([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+-]?\.\d+)\s*([a-z%]*)", re.IGNORECASE
)


def parse_number(value: Any, unit: str | None = None) -> Decimal | None:
    """A number, optionally followed by the field's unit or that unit with a "k" prefix.

    Price lists write ``28W``, ``14KG``, ``24AH``, ``10KVA``: with unit W, kg, Ah, VA these
    read as 28, 14, 24 and 10000. Any other suffix, or text, gives None.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | Decimal):
        return Decimal(value)
    match = _NUMBER_WITH_UNIT_RE.fullmatch(to_halfwidth(str(value)).strip())
    if not match:
        return None
    try:
        number = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    suffix = match.group(2).lower()
    if not suffix:
        return number
    if unit and suffix == unit.lower():
        return number
    if unit and suffix == f"k{unit.lower()}":
        return number * 1000
    return None


def normalize_number(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        value = str(value)
    try:
        return _decimal_str(Decimal(to_halfwidth(str(value)).strip()))
    except InvalidOperation:
        return normalize_text(value)


def normalize_bool(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return "1" if normalize_text(value) in ("1", "true", "yes", "y", "是", "有") else "0"


def brand_key(value: Any) -> str:
    """Lookup key for brand aliases: normalized, with all whitespace removed."""
    return re.sub(r"\s+", "", normalize_text(value))


def brand_candidates(value: Any) -> list[str]:
    """Strings to try when resolving a brand cell.

    Source cells often carry both names: '江波龙（Airdisk）', '沃存(Wodposit)'.
    """
    full = brand_key(value)
    if not full:
        return []
    out = [full]
    match = re.fullmatch(r"(.+?)\((.+?)\)", full)
    if match:
        out.extend([match.group(1), match.group(2)])
    return out


def normalize_value(attr_type: str, value: Any, resolve_brand: BrandResolver | None = None) -> str:
    if attr_type == "capacity":
        return normalize_capacity(value)
    if attr_type == "frequency":
        return normalize_frequency(value)
    if attr_type == "form_factor":
        return normalize_form_factor(value)
    if attr_type == "interface":
        return normalize_interface(value)
    if attr_type in ("number", "int"):
        return normalize_number(value)
    if attr_type == "bool":
        return normalize_bool(value)
    if attr_type == "brand":
        if resolve_brand is not None and value not in (None, ""):
            canonical = resolve_brand(str(value))
            if canonical:
                return normalize_text(canonical)
        return brand_key(value)
    return normalize_text(value)


def fingerprint_parts(
    category_code: str,
    brand_canonical: str | None,
    schema: Iterable[dict[str, Any]],
    attributes: dict[str, Any],
    resolve_brand: BrandResolver | None = None,
    name_zh: str | None = None,
) -> list[str]:
    attr_parts = [
        normalize_value(field.get("type", "text"), attributes.get(field["key"]), resolve_brand)
        for field in schema
        if field.get("in_fingerprint")
    ]
    if not any(attr_parts):
        # No identifying attribute filled (typical for manual or generic items):
        # fall back to the name so distinct items don't collapse into one product.
        attr_parts = [brand_key(name_zh)]
    return [normalize_text(category_code), normalize_text(brand_canonical), *attr_parts]


def compute_fingerprint(
    category_code: str,
    brand_canonical: str | None,
    schema: Iterable[dict[str, Any]],
    attributes: dict[str, Any],
    resolve_brand: BrandResolver | None = None,
    name_zh: str | None = None,
    erp_qualifier: str | None = None,
) -> str:
    """``erp_qualifier`` sets apart a product whose attributes equal those of another
    product with a different ERP code: ERP codes are authoritative identity."""
    parts = fingerprint_parts(
        category_code, brand_canonical, schema, attributes, resolve_brand, name_zh
    )
    if erp_qualifier:
        parts.append(f"erp:{to_halfwidth(erp_qualifier).strip().upper()}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def split_erp_codes(value: Any) -> list[str]:
    """'E.I.P.0000455/E.I.P.0000456' -> both codes; '/', '-', blanks -> []."""
    if value is None:
        return []
    codes = []
    for part in re.split(r"[/,;，、\s]+", to_halfwidth(str(value))):
        part = part.strip()
        if part and part not in ("-", "/") and re.search(r"[A-Za-z0-9]", part):
            codes.append(part.upper())
    return codes
