from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Brand, BrandAlias
from app.services.importer.normalize import brand_candidates, brand_key


class BrandResolver:
    """Resolves any spelling of a brand (Chinese, English, 'zh(en)') to a Brand."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._by_key: dict[str, Brand] = {}
        for brand in session.scalars(select(Brand)):
            self._by_key.setdefault(brand_key(brand.canonical), brand)
            for name in (brand.name_en, brand.name_zh):
                if name:
                    self._by_key.setdefault(brand_key(name), brand)
        for alias in session.scalars(select(BrandAlias)):
            self._by_key[alias.alias_key] = alias.brand

    def find(self, text: str | None) -> Brand | None:
        for candidate in brand_candidates(text):
            brand = self._by_key.get(candidate)
            if brand is not None:
                return brand
        return None

    def canonical(self, text: str) -> str | None:
        brand = self.find(text)
        return brand.canonical if brand else None


def add_alias(session: Session, brand: Brand, alias: str, lang: str = "en") -> BrandAlias:
    row = BrandAlias(brand=brand, alias=alias.strip(), alias_key=brand_key(alias), lang=lang)
    session.add(row)
    return row
