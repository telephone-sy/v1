from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth import get_current_user
from database import get_db
from models import Favorite, Listing, User
from schemas import ListingOut
from routers.listings import serialize_listing


router = APIRouter(prefix="/api/favorites", tags=["المفضلة"])


@router.get("", response_model=list[ListingOut])
def list_favorites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.scalars(
        select(Listing)
        .join(Favorite, Favorite.listing_id == Listing.id)
        .options(selectinload(Listing.images))
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    ).all()
    return [serialize_listing(item) for item in items]


@router.post("/{listing_id}", status_code=status.HTTP_201_CREATED)
def add_favorite(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Listing, listing_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الإعلان غير موجود")
    existing = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.listing_id == listing_id))
    if not existing:
        db.add(Favorite(user_id=user.id, listing_id=listing_id))
        db.commit()
    return {"listing_id": listing_id, "is_favorite": True}


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    favorite = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.listing_id == listing_id))
    if favorite:
        db.delete(favorite)
        db.commit()