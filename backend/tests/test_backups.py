"""Backups: create, download, upload, restore, delete (plan §9, M6)."""

from __future__ import annotations

import io
import zipfile

from tests.test_quotes import API, png_bytes


def product_names(client) -> list[str]:
    return [p["name_zh"] for p in client.get(f"{API}/products").json()["items"]]


def add_product(client, categories, name: str) -> dict:
    res = client.post(
        f"{API}/products",
        json={"category_id": categories["ups"]["id"], "name_zh": name, "attributes": {}},
    )
    assert res.status_code == 201, res.json()
    return res.json()


def test_database_backup_and_restore(client, categories, data_dir):
    add_product(client, categories, "保留的产品")
    made = client.post(f"{API}/backups", json={}).json()
    assert made["kind"] == "database" and made["name"].startswith("manual-")

    add_product(client, categories, "之后的产品")
    assert "之后的产品" in product_names(client)

    res = client.post(f"{API}/backups/{made['name']}/restore")
    assert res.status_code == 200, res.json()
    safety = res.json()
    assert safety["name"].startswith("before-restore-")
    assert product_names(client) == ["保留的产品"]

    # the restore itself can be undone
    client.post(f"{API}/backups/{safety['name']}/restore")
    assert set(product_names(client)) == {"保留的产品", "之后的产品"}

    names = [b["name"] for b in client.get(f"{API}/backups").json()]
    assert made["name"] in names and safety["name"] in names
    download = client.get(f"{API}/backups/{made['name']}/download")
    assert download.content[:15] == b"SQLite format 3"
    assert client.delete(f"{API}/backups/{made['name']}").status_code == 204
    assert client.get(f"{API}/backups/{made['name']}/download").status_code == 404


def test_full_backup_brings_back_photos_and_settings(client, categories, data_dir):
    product = add_product(client, categories, "带图片的产品")
    client.post(f"{API}/products/{product['id']}/images", files={"files": ("a.png", png_bytes())})
    client.put(f"{API}/settings", json={"offer_prefix": "ABC"})
    made = client.post(f"{API}/backups", json={"full": True}).json()
    assert made["kind"] == "full"
    with zipfile.ZipFile(data_dir / "backups" / made["name"]) as zf:
        names = zf.namelist()
    assert "app.db" in names and "settings.json" in names
    assert any(n.startswith("images/") for n in names) and ".env" not in names

    for path in (data_dir / "images").rglob("*"):
        if path.is_file():
            path.unlink()
    client.put(f"{API}/settings", json={"offer_prefix": "XYZ"})

    assert client.post(f"{API}/backups/{made['name']}/restore").status_code == 200
    assert client.get(f"{API}/settings").json()["offer_prefix"] == "ABC"
    image_id = client.get(f"{API}/products/{product['id']}").json()["image_ids"][0]
    assert client.get(f"{API}/images/{image_id}").status_code == 200


def test_upload_accepts_only_backups(client, data_dir):
    bad = client.post(f"{API}/backups/upload", files={"file": ("x.db", b"not a database")})
    assert bad.status_code == 422 and bad.json()["key"] == "backup.invalid"
    made = client.post(f"{API}/backups", json={}).json()
    content = (data_dir / "backups" / made["name"]).read_bytes()
    good = client.post(f"{API}/backups/upload", files={"file": ("old.db", content)})
    assert good.status_code == 201 and good.json()["name"].startswith("uploaded-")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("readme.txt", "hello")
    res = client.post(f"{API}/backups/upload", files={"file": ("x.zip", buffer.getvalue())})
    assert res.status_code == 422
