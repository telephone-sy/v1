from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from auth import password_hash
from database import Base
from models import AuthSession, User, utcnow
from services.create_admin import ensure_admin


def test_admin_setup_creates_or_resets_credentials():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        existing = User(
            name="عضو",
            phone="0912345678",
            password_hash=password_hash.hash("OldPassword123"),
        )
        db.add(existing)
        db.commit()
        db.add(AuthSession(user_id=existing.id, token_hash="a" * 64, expires_at=utcnow()))
        db.commit()

        ensure_admin(db, existing.phone, "مشرف", "NewPassword123")
        db.commit()
        db.refresh(existing)

        assert existing.role == "admin"
        assert existing.is_active is True
        assert password_hash.verify("NewPassword123", existing.password_hash)
        assert not password_hash.verify("OldPassword123", existing.password_hash)
        assert db.scalar(select(AuthSession).where(AuthSession.user_id == existing.id)) is None
    engine.dispose()