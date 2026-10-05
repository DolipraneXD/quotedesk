"""Runtime paths and user settings.

Settings live in ``data/settings.json`` (edited from the UI). The AI provider keys
(Anthropic, Google Gemini, Groq, Inception) are the exception: they are kept in
``data/.env`` and never returned to the browser.
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field

HOST = "127.0.0.1"  # no auth, so never listen on another interface
PORT = 8765

REPO_DIR = Path(__file__).resolve().parents[2]
# The desktop build (PyInstaller) unpacks read-only files (interface, migrations, fonts) to
# sys._MEIPASS; the data folder sits next to the executable so it survives updates.
FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", REPO_DIR))
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else REPO_DIR
FRONTEND_DIST = BUNDLE_DIR / "frontend" / "dist"

LlmProvider = Literal["anthropic", "google", "groq", "inception"]
API_KEY_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "inception": "INCEPTION_API_KEY",
}


def data_dir() -> Path:
    """Read on every call so tests can point QUOTEDESK_DATA_DIR at a temp dir."""
    return Path(os.environ.get("QUOTEDESK_DATA_DIR") or APP_DIR / "data")


def db_path() -> Path:
    return data_dir() / "app.db"


def ensure_data_dirs() -> None:
    for sub in ("", "imports", "exports", "backups", "logs", "images"):
        (data_dir() / sub).mkdir(parents=True, exist_ok=True)


class CompanySettings(BaseModel):
    name_en: str = "Shenzhen Sixunited technology Co.,Ltd"
    name_zh: str = ""
    address_en: str = (
        "33/34/35F, Building F, Tongfang Kexing Science Park, Nanshan District, Shenzhen"
    )
    address_zh: str = ""
    logo_image_id: int | None = None  # images table; printed at the top left of documents
    phone: str = ""
    email: str = ""
    # bank details printed on proforma invoices (placeholders until the owner fills them)
    bank_account_name: str = ""
    bank_account_no: str = ""
    bank_name: str = ""
    bank_swift: str = ""
    # seller contact on proforma invoices
    seller_name: str = ""
    seller_phone: str = ""
    seller_email: str = ""
    signature_image_id: int | None = None


class AppSettings(BaseModel):
    company: CompanySettings = Field(default_factory=CompanySettings)
    offer_prefix: str = "WKZ"
    pi_prefix: str = "PI"
    pi_payment_term: str = (
        "Price based on {trade_term}. 60% deposit shall be paid by (T/T) upon confirmation of "
        "the order. The remaining 40% of the total amount must be settled by T/T prior to "
        "shipment."
    )
    pi_lead_time: str = (
        "55 working days, calculated from the date of receipt of the advance payment"
    )
    pi_delivery_place: str = (
        "The goods shall be either collected by buyer or delivered to the address of the "
        "domestic designated freight forwarder in Shenzhen as specified by buyer"
    )
    pi_warranty: str = (
        "The warranty period for this product is 12 months from the date of delivery."
    )
    price_age_warning_days: int = 30
    default_margin_pct: Decimal = Decimal("0")
    default_fx_rate_cny_usd: Decimal = Decimal("7.10")
    default_validity_days: int = 30
    llm_provider: LlmProvider = "anthropic"
    llm_model: str = "claude-sonnet-5-5"  # Anthropic model
    gemini_model: str = "gemini-3.8-flash"
    groq_model: str = "qwen/qwen3.8-27b"  # the Groq model with vision and strict JSON schema
    inception_model: str = "mercury-2.5"  # text only: no screenshots or scanned pages
    ui_language: str = "zh"
    rounding: int = 2
    backup_retention: int = 30


def settings_path() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> AppSettings:
    path = settings_path()
    if path.exists():
        return AppSettings.model_validate_json(path.read_text(encoding="utf-8"))
    return AppSettings()


def save_settings(settings: AppSettings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def env_path() -> Path:
    return data_dir() / ".env"


def active_model(settings: AppSettings) -> str:
    return {
        "anthropic": settings.llm_model,
        "google": settings.gemini_model,
        "groq": settings.groq_model,
        "inception": settings.inception_model,
    }[settings.llm_provider]


def get_api_key(provider: LlmProvider = "anthropic") -> str | None:
    var = API_KEY_VARS[provider]
    if os.environ.get(var):
        return os.environ[var]
    path = env_path()
    if path.exists():
        return dotenv_values(path).get(var) or None
    return None


def set_api_key(key: str | None, provider: LlmProvider = "anthropic") -> None:
    var = API_KEY_VARS[provider]
    path = env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if path.exists():
        lines = [
            ln
            for ln in path.read_text(encoding="utf-8").splitlines()
            if not ln.startswith(f"{var}=")
        ]
    if key:
        lines.append(f"{var}={key}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # best effort on Windows
        pass
