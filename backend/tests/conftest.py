from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import reset_engine, session_factory

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("QUOTEDESK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("INCEPTION_API_KEY", raising=False)
    reset_engine()
    yield tmp_path
    reset_engine()


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def session(client: TestClient) -> Iterator[Session]:
    with session_factory()() as db:
        yield db


@pytest.fixture
def categories(client: TestClient) -> dict[str, dict]:
    return {c["code"]: c for c in client.get("/api/v1/categories").json()}


# shared by the quote and configuration tests
@pytest.fixture
def ups(client: TestClient, categories: dict[str, dict]) -> dict:
    """The UPS of the offer sample, priced at cost 400."""
    res = client.post(
        "/api/v1/products",
        json={
            "category_id": categories["ups"]["id"],
            "name_zh": "SP10KS 在线式UPS",
            "name_en": "SP10KS",
            "attributes": {"model": "SP10KS"},
            "description_en": "High-frequency on-line UPS, power 10KVA/5400W\nweight:14KG",
            "model_no": "SP10KS",
            "price_usd": "400",
            "max_order_qty": 50,
        },
    )
    assert res.status_code == 201, res.json()
    return res.json()


@pytest.fixture
def customer(client: TestClient) -> dict:
    res = client.post(
        "/api/v1/customers",
        json={"code": "sp002", "name": "Linux Technology SL", "contact_name": "David",
              "email": "david@example.com", "trade_term": "FOB Shenzhen"},
    )  # fmt: skip
    assert res.status_code == 201, res.json()
    return res.json()
