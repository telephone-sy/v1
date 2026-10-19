from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth import enforce_rate_limit, get_current_user
from database import get_db
from models import Listing, Report, User
from schemas import ReportCreate


router = APIRouter(prefix="/api/reports", tags=["البلاغات"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_report(
    payload: ReportCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, "report", 5, 3600)
    if not db.get(Listing, payload.listing_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الإعلان غير موجود")
    report = Report(
        listing_id=payload.listing_id,
        reporter_id=user.id,
        reason=payload.reason.strip(),
        details=payload.details.strip(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "status": report.status, "message": "تم استلام البلاغ"}