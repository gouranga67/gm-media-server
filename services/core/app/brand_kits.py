from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from psycopg.errors import UniqueViolation

from app.database import connection
from app.schemas import BrandKitCreate, BrandKitResponse

router = APIRouter(prefix="/api/v1", tags=["brand-kits"])


@router.get("/brand-kits", response_model=list[BrandKitResponse])
def list_brand_kits() -> list[dict[str, Any]]:
    with connection() as database:
        return list(database.execute("SELECT * FROM brand_kits ORDER BY updated_at DESC, lower(name)").fetchall())


def _values(payload: BrandKitCreate) -> tuple[str, str, str, str, str]:
    return (payload.name, payload.primary_color.upper(), payload.accent_color.upper(), payload.caption_style, payload.font_family)


@router.post("/brand-kits", response_model=BrandKitResponse, status_code=status.HTTP_201_CREATED)
def create_brand_kit(payload: BrandKitCreate) -> dict[str, Any]:
    try:
        with connection() as database:
            row = database.execute(
                "INSERT INTO brand_kits (name, primary_color, accent_color, caption_style, font_family) VALUES (%s, %s, %s, %s, %s) RETURNING *",
                _values(payload),
            ).fetchone()
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="a brand kit with that name already exists") from error
    assert row is not None
    return row


@router.put("/brand-kits/{brand_kit_id}", response_model=BrandKitResponse)
def update_brand_kit(brand_kit_id: UUID, payload: BrandKitCreate) -> dict[str, Any]:
    try:
        with connection() as database:
            row = database.execute(
                "UPDATE brand_kits SET name=%s, primary_color=%s, accent_color=%s, caption_style=%s, font_family=%s, updated_at=now() WHERE id=%s RETURNING *",
                (*_values(payload), brand_kit_id),
            ).fetchone()
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="a brand kit with that name already exists") from error
    if row is None:
        raise HTTPException(status_code=404, detail="brand kit not found")
    return row


@router.delete("/brand-kits/{brand_kit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand_kit(brand_kit_id: UUID) -> Response:
    with connection() as database:
        deleted = database.execute("DELETE FROM brand_kits WHERE id=%s", (brand_kit_id,))
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="brand kit not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
