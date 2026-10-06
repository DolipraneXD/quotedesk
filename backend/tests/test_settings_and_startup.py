import sqlite3
from contextlib import closing
from types import SimpleNamespace

API = "/api/v1"


def test_settings_roundtrip_and_api_key_never_returned(client, data_dir):
    settings = client.get(f"{API}/settings").json()
    assert settings["offer_prefix"] == "WKZ"
    assert settings["anthropic_api_key_set"] is False
    assert "anthropic_api_key" not in settings

    settings.update(offer_prefix="ABC", anthropic_api_key="sk-ant-test-123")
    res = client.put(f"{API}/settings", json=settings)
    body = res.json()
    assert body["offer_prefix"] == "ABC"
    assert body["anthropic_api_key_set"] is True
    assert "sk-ant-test-123" not in res.text
    assert "sk-ant-test-123" not in (data_dir / "settings.json").read_text()
    assert "sk-ant-test-123" in (data_dir / ".env").read_text()

    # omitting the key leaves it unchanged; empty string removes it
    body.pop("anthropic_api_key_set")
    assert client.put(f"{API}/settings", json=body).json()["anthropic_api_key_set"] is True
    body["anthropic_api_key"] = ""
    assert client.put(f"{API}/settings", json=body).json()["anthropic_api_key_set"] is False


def test_gemini_key_and_provider(client, data_dir):
    settings = client.get(f"{API}/settings").json()
    assert settings["llm_provider"] == "anthropic"
    assert settings["gemini_model"] == "gemini-3.8-flash"
    assert settings["gemini_api_key_set"] is False

    settings.update(llm_provider="google", gemini_api_key="AIza-test-456")
    res = client.put(f"{API}/settings", json=settings)
    body = res.json()
    assert body["llm_provider"] == "google"
    assert body["gemini_api_key_set"] is True and body["anthropic_api_key_set"] is False
    assert "AIza-test-456" not in res.text
    assert "GEMINI_API_KEY=AIza-test-456" in (data_dir / ".env").read_text()

    settings["llm_provider"] = "openai"
    assert client.put(f"{API}/settings", json=settings).status_code == 422


def test_test_llm_uses_the_selected_provider(client, monkeypatch):
    from google.genai import errors as genai_errors

    from app.api import settings as settings_api

    class FakeModels:
        def __init__(self, outcome):
            self.outcome = outcome

        def generate_content(self, **kwargs):
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return SimpleNamespace(model_version=kwargs["model"])

    def use(outcome):
        monkeypatch.setattr(
            settings_api.genai,
            "Client",
            lambda **kwargs: SimpleNamespace(models=FakeModels(outcome)),
        )

    settings = client.get(f"{API}/settings").json()
    settings.update(llm_provider="google")
    client.put(f"{API}/settings", json=settings)
    assert client.post(f"{API}/settings/test-llm").json()["key"] == "import.no_api_key"

    settings.update(gemini_api_key="AIza-test")
    client.put(f"{API}/settings", json=settings)
    use(None)
    assert client.post(f"{API}/settings/test-llm").json() == {
        "ok": True, "model": "gemini-3.8-flash", "detail": "ok",
    }  # fmt: skip
    bad_key = {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT",
                         "details": [{"reason": "API_KEY_INVALID"}]}}  # fmt: skip
    use(genai_errors.ClientError(400, bad_key))
    assert client.post(f"{API}/settings/test-llm").json()["detail"] == "auth"
    use(genai_errors.ClientError(404, {"error": {"message": "no model", "status": "NOT_FOUND"}}))
    assert client.post(f"{API}/settings/test-llm").json()["detail"] == "model_not_found"
    use(ConnectionError("down"))
    assert client.post(f"{API}/settings/test-llm").json()["detail"] == "network"


def test_groq_provider(client, data_dir, monkeypatch):
    from app.api import settings as settings_api

    settings = client.get(f"{API}/settings").json()
    assert settings["groq_model"] == "qwen/qwen3.8-27b"
    settings.update(llm_provider="groq", groq_api_key="gsk-test-789")
    body = client.put(f"{API}/settings", json=settings).json()
    assert body["groq_api_key_set"] is True and "gsk-test-789" not in str(body)
    assert "GROQ_API_KEY=gsk-test-789" in (data_dir / ".env").read_text()

    created = {}

    def fake_groq(**kwargs):
        created.update(kwargs)
        create = lambda **kw: SimpleNamespace(model=kw["model"])  # noqa: E731
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(settings_api.groq, "Groq", fake_groq)
    assert client.post(f"{API}/settings/test-llm").json() == {
        "ok": True, "model": "qwen/qwen3.8-27b", "detail": "ok",
    }  # fmt: skip
    assert created["api_key"] == "gsk-test-789"


def test_inception_provider(client, data_dir, monkeypatch):
    import httpx

    from app.api import settings as settings_api

    settings = client.get(f"{API}/settings").json()
    assert settings["inception_model"] == "mercury-2.5"
    settings.update(llm_provider="inception", inception_api_key="sk_test_321")
    body = client.put(f"{API}/settings", json=settings).json()
    assert body["inception_api_key_set"] is True and "sk_test_321" not in str(body)
    assert "INCEPTION_API_KEY=sk_test_321" in (data_dir / ".env").read_text()

    sent = {}
    reply = httpx.Response(200, json={"model": "mercury-2.5"})

    def fake_post(url, **kwargs):
        sent.update(kwargs)
        return reply

    monkeypatch.setattr(settings_api.httpx, "post", fake_post)
    assert client.post(f"{API}/settings/test-llm").json() == {
        "ok": True, "model": "mercury-2.5", "detail": "ok",
    }  # fmt: skip
    assert sent["headers"]["Authorization"] == "Bearer sk_test_321"
    reply = httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})
    assert client.post(f"{API}/settings/test-llm").json()["detail"] == "auth"
    reply = httpx.Response(400, text="Value error, Model must be one of the following: ...")
    assert client.post(f"{API}/settings/test-llm").json()["detail"] == "model_not_found"


def test_language_switch_persists(client):
    assert (
        client.put(f"{API}/settings/language", json={"ui_language": "en"}).json()["ui_language"]
        == "en"
    )
    assert client.get(f"{API}/settings").json()["ui_language"] == "en"


def test_startup_creates_db_dirs_and_backup(data_dir):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()):
        pass
    assert (data_dir / "app.db").exists()
    assert not list((data_dir / "backups").glob("*.db"))  # nothing to back up on first run
    with TestClient(create_app()):
        pass
    backups = list((data_dir / "backups").glob("app-*.db"))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as db:
        assert db.execute("select count(*) from categories").fetchone()[0] == 23


def test_migrations_downgrade_and_upgrade(client, data_dir):
    from alembic import command
    from alembic.config import Config

    from app.migrate import BACKEND_DIR

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logging"] = False
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(data_dir / "app.db")) as db:
        tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    assert {"products", "products_fts", "price_history", "brand_aliases"} <= tables


def test_server_binds_localhost_only():
    from app.config import HOST

    assert HOST == "127.0.0.1"
