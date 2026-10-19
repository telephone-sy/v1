import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import get_admin
from database import get_db
from models import AdminAction, AuthSession, Listing, Report, User
from schemas import UserOut
from services.images import delete_images


router = APIRouter(prefix="/api/admin", tags=["الإدارة"])


def audit(db: Session, admin: User, action: str, target_type: str, target_id: int) -> None:
    db.add(AdminAction(admin_id=admin.id, action=action, target_type=target_type, target_id=str(target_id)))


@router.get("/stats")
def stats(_admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    return {
        "users": db.scalar(select(func.count()).select_from(User)),
        "listings": db.scalar(select(func.count()).select_from(Listing)),
        "sold": db.scalar(select(func.count()).select_from(Listing).where(Listing.is_sold.is_(True))),
        "open_reports": db.scalar(select(func.count()).select_from(Report).where(Report.status == "open")),
    }


@router.get("/users", response_model=list[UserOut])
def users(_admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all()


@router.patch("/users/{user_id}/active")
def set_user_active(user_id: int, active: bool, admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    if target.id == admin.id and not active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "لا يمكن تعطيل حسابك الحالي")
    target.is_active = active
    if not active:
        db.query(AuthSession).filter(AuthSession.user_id == target.id).delete(synchronize_session=False)
    audit(db, admin, "user_active" if active else "user_disabled", "user", user_id)
    db.commit()
    return {"id": target.id, "is_active": target.is_active}


@router.get("/reports")
def reports(_admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    return db.scalars(select(Report).order_by(Report.created_at.desc()).limit(500)).all()


@router.patch("/reports/{report_id}")
def update_report(report_id: int, status_value: str, admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    if status_value not in {"open", "reviewed", "dismissed"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "حالة البلاغ غير صالحة")
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "البلاغ غير موجود")
    report.status = status_value
    audit(db, admin, "report_status", "report", report_id)
    db.commit()
    return {"id": report.id, "status": report.status}


@router.get("/actions")
def actions(_admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    return db.scalars(select(AdminAction).order_by(AdminAction.created_at.desc()).limit(500)).all()


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_listing(listing_id: int, admin: User = Depends(get_admin), db: Session = Depends(get_db)):
    item = db.get(Listing, listing_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الإعلان غير موجود")
    image_paths = [image.path for image in item.images]
    audit(db, admin, "listing_deleted", "listing", listing_id)
    db.delete(item)
    db.commit()
    upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads")).resolve()
    delete_images(image_paths, upload_dir)