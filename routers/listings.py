from decimal import Decimal
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from auth import enforce_rate_limit, get_current_user
from database import get_db
from models import Listing, ListingImage, User
from schemas import ListingCreate, ListingOut, ListingUpdate
from services.images import delete_images, save_images


router = APIRouter(prefix="/api/listings", tags=["الإعلانات"])
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads")).resolve()


def serialize_listing(item: Listing) -> dict:
    return {
        "id": item.id,
        "owner_id": item.owner_id,
        "title": item.title,
        "brand": item.brand,
        "model": item.model,
        "price": format(item.price, "f"),
        "currency": item.currency,
        "city": item.city,
        "region": item.region,
        "condition": item.condition,
        "description": item.description,
        "seller_name": item.seller_name,
        "contact_phone": item.contact_phone,
        "storage_gb": item.storage_gb,
        "ram_gb": item.ram_gb,
        "is_sold": item.is_sold,
        "views": item.views,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "images": [f"/uploads/{image.path}" for image in item.images],
    }


def fetch_listing(db: Session, listing_id: int) -> Listing:
    item = db.scalar(select(Listing).options(selectinload(Listing.images)).where(Listing.id == listing_id))
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الإعلان غير موجود")
    return item


def require_owner(item: Listing, user: User) -> None:
    if item.owner_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "لا تملك صلاحية تعديل هذا الإعلان")


@router.get("", response_model=list[ListingOut])
def list_listings(
    request: Request,
    q: str | None = Query(default=None, max_length=120),
    brand: str | None = Query(default=None, max_length=60),
    model: str | None = Query(default=None, max_length=100),
    seller_name: str | None = Query(default=None, max_length=120),
    city: str | None = Query(default=None, max_length=80),
    region: str | None = Query(default=None, max_length=80),
    condition: str | None = Query(default=None, pattern="^(new|used)$"),
    currency: str | None = Query(default=None, pattern="^(SYP|USD)$"),
    min_price: Decimal | None = Query(default=None, gt=0),
    max_price: Decimal | None = Query(default=None, gt=0),
    sold: bool | None = None,
    sort: str = Query(default="newest", pattern="^(newest|price_asc|price_desc)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, "public_listing_read", 120)
    if (min_price is not None or max_price is not None or sort != "newest") and currency is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "حدد العملة عند فرز الأسعار أو تحديد نطاقها")
    query = select(Listing).options(selectinload(Listing.images))
    if q:
        term = f"%{q.strip()}%"
        query = query.where(or_(Listing.title.ilike(term), Listing.brand.ilike(term), Listing.model.ilike(term)))
    if brand:
        query = query.where(Listing.brand == brand)
    if model:
        query = query.where(Listing.model.ilike(f"%{model}%"))
    if seller_name:
        query = query.where(Listing.seller_name.ilike(f"%{seller_name}%"))
    if city:
        query = query.where(Listing.city == city)
    if region:
        query = query.where(Listing.region == region)
    if condition:
        query = query.where(Listing.condition == condition)
    if currency:
        query = query.where(Listing.currency == currency)
    if min_price is not None:
        query = query.where(Listing.price >= min_price)
    if max_price is not None:
        query = query.where(Listing.price <= max_price)
    if sold is not None:
        query = query.where(Listing.is_sold == sold)
    ordering = Listing.price.asc() if sort == "price_asc" else Listing.price.desc() if sort == "price_desc" else Listing.created_at.desc()
    items = db.scalars(query.order_by(ordering).offset(offset).limit(limit)).all()
    return [serialize_listing(item) for item in items]


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: int, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "public_listing_read", 120)
    item = fetch_listing(db, listing_id)
    item.views += 1
    db.commit()
    return serialize_listing(item)


@router.post("", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
def create_listing(
    payload: ListingCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, "listing_create", 10, 3600)
    item = Listing(
        owner_id=user.id,
        title=f"{payload.brand} {payload.model}",
        **payload.model_dump(),
    )
    db.add(item)
    db.commit()
    return serialize_listing(fetch_listing(db, item.id))


@router.patch("/{listing_id}", response_model=ListingOut)
def update_listing(
    listing_id: int,
    payload: ListingUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = fetch_listing(db, listing_id)
    require_owner(item, user)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    if "brand" in changes or "model" in changes:
        item.title = f"{item.brand} {item.model}"
    db.commit()
    return serialize_listing(fetch_listing(db, item.id))


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_listing(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = fetch_listing(db, listing_id)
    require_owner(item, user)
    paths = [image.path for image in item.images]
    db.delete(item)
    db.commit()
    delete_images(paths, UPLOAD_DIR)


@router.patch("/{listing_id}/sold")
def mark_sold(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = fetch_listing(db, listing_id)
    require_owner(item, user)
    item.is_sold = not item.is_sold
    db.commit()
    return {"id": item.id, "is_sold": item.is_sold}


@router.post("/{listing_id}/images", response_model=ListingOut)
async def replace_images(
    listing_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, "image_upload", 10, 3600)
    item = fetch_listing(db, listing_id)
    require_owner(item, user)
    paths = await save_images(files, UPLOAD_DIR)
    old_paths = [image.path for image in item.images]
    try:
        item.images.clear()
        item.images.extend(ListingImage(path=path, position=index) for index, path in enumerate(paths))
        db.commit()
    except Exception:
        db.rollback()
        delete_images(paths, UPLOAD_DIR)
        raise
    delete_images(old_paths, UPLOAD_DIR)
    return serialize_listing(fetch_listing(db, listing_id))