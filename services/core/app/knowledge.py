from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.database import connection
from app.productization import actor_login, require_editor, require_owner

router = APIRouter(prefix="/api/v1/library", tags=["source knowledge"])


class ProductIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=2000)

    @field_validator("name", "aliases")
    @classmethod
    def clean(cls, value):
        if isinstance(value, list):
            values = list(dict.fromkeys(" ".join(v.split()) for v in value))
            if any(not v or len(v)>120 for v in values):
                raise ValueError("aliases must be short nonempty names")
            return values
        value = " ".join(value.split())
        if not value:
            raise ValueError("give the product a name")
        return value


class RangeAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)
    role: Literal["talking", "broll", "product", "reaction", "avoid"]
    note: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def forward(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("the marked range must move forward")
        return self


@router.get("/knowledge")
def knowledge():
    with connection() as database:
        products = list(database.execute("SELECT * FROM source_products ORDER BY name LIMIT 100").fetchall())
    return {"products": products, "evidence_version": "1.0", "hosted_model_calls": 0,
            "note": "Names and aliases help recognize mentions. They do not verify every pictured product or claim."}


@router.put("/products/{product_id}")
def save_product(product_id: UUID, payload: ProductIdentity, x_gm_user_login: str | None = Header(default=None)):
    require_owner(actor_login(x_gm_user_login))
    try:
        with connection() as database:
            database.execute("LOCK TABLE source_products IN SHARE ROW EXCLUSIVE MODE")
            existing = database.execute("SELECT id FROM source_products WHERE id=%s", (product_id,)).fetchone()
            count = database.execute("SELECT count(*) AS n FROM source_products").fetchone()
            if not existing and count["n"] >= 100:
                raise HTTPException(status_code=422, detail="the dictionary already contains 100 products")
            row = database.execute("""INSERT INTO source_products (id,name,aliases,notes) VALUES (%s,%s,%s,%s)
                ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,aliases=EXCLUDED.aliases,
                notes=EXCLUDED.notes,updated_at=now() RETURNING *""",
                (product_id,payload.name,payload.aliases,payload.notes)).fetchone()
    except UniqueViolation as error:
        raise HTTPException(status_code=409, detail="a product with that name already exists") from error
    return row


@router.delete("/products/{product_id}")
def delete_product(product_id: UUID, x_gm_user_login: str | None = Header(default=None)):
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        database.execute("DELETE FROM source_products WHERE id=%s", (product_id,))
    return {"removed": str(product_id), "media_changed": False}


@router.get("/assets/{asset_id}/ranges")
def source_ranges(asset_id: UUID):
    with connection() as database:
        return list(database.execute("SELECT * FROM asset_range_annotations WHERE asset_id=%s ORDER BY start_seconds LIMIT 40", (asset_id,)).fetchall())


@router.put("/assets/{asset_id}/ranges/{annotation_id}")
def save_range(asset_id: UUID, annotation_id: UUID, payload: RangeAnnotation,
               x_gm_user_login: str | None = Header(default=None)):
    require_editor(actor_login(x_gm_user_login))
    if annotation_id != payload.id:
        raise HTTPException(status_code=422, detail="range identifier mismatch")
    with connection() as database:
        source = database.execute("""SELECT i.manifest FROM assets a JOIN asset_ingests i ON i.asset_id=a.id
            WHERE a.id=%s AND a.status='ready' AND a.library_status='active' FOR UPDATE OF a""", (asset_id,)).fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="active source not found")
        duration = float(source["manifest"].get("probe", {}).get("format", {}).get("duration_seconds") or 0)
        if payload.end_seconds > duration:
            raise HTTPException(status_code=422, detail="range exceeds the source duration")
        count = database.execute("SELECT count(*) AS n FROM asset_range_annotations WHERE asset_id=%s AND id<>%s", (asset_id,annotation_id)).fetchone()
        if count and count["n"] >= 40:
            raise HTTPException(status_code=422, detail="this source already has 40 marked ranges")
        existing = database.execute("SELECT asset_id FROM asset_range_annotations WHERE id=%s", (annotation_id,)).fetchone()
        if existing and existing["asset_id"] != asset_id:
            raise HTTPException(status_code=409, detail="range belongs to another source")
        row = database.execute("""INSERT INTO asset_range_annotations(id,asset_id,start_seconds,end_seconds,role,note)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET start_seconds=EXCLUDED.start_seconds,
            end_seconds=EXCLUDED.end_seconds,role=EXCLUDED.role,note=EXCLUDED.note RETURNING *""",
            (annotation_id,asset_id,payload.start_seconds,payload.end_seconds,payload.role,payload.note)).fetchone()
    return row


@router.delete("/assets/{asset_id}/ranges/{annotation_id}")
def delete_range(asset_id: UUID, annotation_id: UUID, x_gm_user_login: str | None = Header(default=None)):
    require_editor(actor_login(x_gm_user_login))
    with connection() as database:
        database.execute("DELETE FROM asset_range_annotations WHERE id=%s AND asset_id=%s", (annotation_id,asset_id))
    return {"removed": str(annotation_id)}


@router.post("/assets/{asset_id}/refresh-analysis")
def refresh_source_analysis(asset_id: UUID, x_gm_user_login: str | None = Header(default=None)):
    require_owner(actor_login(x_gm_user_login))
    with connection() as database:
        row = database.execute("""UPDATE asset_ingests i SET status='pending',attempts=0,error=NULL,updated_at=now(),
            manifest=jsonb_set(COALESCE(i.manifest,'{}'::jsonb),'{force_reanalysis}','true'::jsonb)
            FROM assets a WHERE i.asset_id=a.id AND a.id=%s AND a.status='ready' AND a.library_status='active'
            AND i.status IN ('ready','failed') RETURNING i.asset_id""", (asset_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=409, detail="source is unavailable or already processing")
    return {"asset_id": str(asset_id), "status": "pending", "hosted_model_calls": 0}
