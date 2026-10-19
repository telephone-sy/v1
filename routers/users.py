from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth import get_current_user
from database import get_db
from models import Listing, User
from schemas import ListingOut
from routers.listings import serialize_listing


router = APIRouter(prefix="/api/users", tags=["المستخدمون"])


@router.get("/me/listings", response_model=list[ListingOut])
def my_listings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.scalars(
        select(Listing)
        .options(selectinload(Listing.images))
        .where(Listing.owner_id == user.id)
        .order_by(Listing.created_at.desc())
    ).all()
    return [serialize_listing(item) for item in items]