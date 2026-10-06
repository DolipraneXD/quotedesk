"""Images: serving, product photos, and the company logo and signature."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import SessionDep
from app.config import load_settings, save_settings
from app.errors import ProblemError
from app.models import Product, ProductImage
from app.services import images

router = APIRouter(tags=["images"])


@router.get("/images/{image_id}")
def get_image(session: SessionDep, image_id: int) -> FileResponse:
    image = images.get_image(session, image_id)
    return FileResponse(
        images.original_path(image),
        media_type=image.media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


def _product(session: SessionDep, product_id: int) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise ProblemError(404, "product.not_found", "Product not found", id=product_id)
    return product


@router.post("/products/{product_id}/images", response_model=list[int], status_code=201)
async def add_product_images(
    session: SessionDep, product_id: int, files: Annotated[list[UploadFile], File()]
) -> list[int]:
    """Photos printed in the quote list's Photo column; returns the product's image ids."""
    product = _product(session, product_id)
    start = session.scalar(
        select(func.coalesce(func.max(ProductImage.sort_order), -1)).where(
            ProductImage.product_id == product_id
        )
    )
    for offset, upload in enumerate(files, start=1):
        image = images.save_image(session, upload.filename, await upload.read())
        product.images.append(
            ProductImage(product_id=product_id, image_id=image.id, sort_order=(start or 0) + offset)
        )
    session.commit()
    session.refresh(product)
    return product.image_ids


@router.delete("/products/{product_id}/images/{image_id}", response_model=list[int])
def remove_product_image(session: SessionDep, product_id: int, image_id: int) -> list[int]:
    """Unlinks the photo; the file stays, since quotes may still print it."""
    product = _product(session, product_id)
    product.images = [link for link in product.images if link.image_id != image_id]
    session.commit()
    session.refresh(product)
    return product.image_ids


@router.put("/products/{product_id}/images", response_model=list[int])
def reorder_product_images(session: SessionDep, product_id: int, image_ids: list[int]) -> list[int]:
    product = _product(session, product_id)
    by_id = {link.image_id: link for link in product.images}
    if sorted(image_ids) != sorted(by_id):
        raise ProblemError(422, "image.bad_order", "List every image once")
    for position, image_id in enumerate(image_ids):
        by_id[image_id].sort_order = position
    session.commit()
    session.refresh(product)
    return product.image_ids


CompanyImage = Literal["logo", "signature"]


@router.post("/settings/images/{kind}", response_model=int, status_code=201)
async def set_company_image(
    session: SessionDep, kind: CompanyImage, file: Annotated[UploadFile, File()]
) -> int:
    image = images.save_image(session, file.filename, await file.read())
    session.commit()
    settings = load_settings()
    setattr(settings.company, f"{kind}_image_id", image.id)
    save_settings(settings)
    return image.id


@router.delete("/settings/images/{kind}", status_code=204)
def clear_company_image(kind: CompanyImage) -> Response:
    settings = load_settings()
    setattr(settings.company, f"{kind}_image_id", None)
    save_settings(settings)
    return Response(status_code=204)
