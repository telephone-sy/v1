from datetime import timedelta
import hashlib
import secrets

from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database import get_db
from models import AuthSession, User, utcnow
from services.rate_limit import enforce_rate_limit


password_hash = PasswordHash.recommended()
SESSION_COOKIE = "telephone_sy_session"
SESSION_TTL = timedelta(days=7)
DUMMY_PASSWORD_HASH = password_hash.hash(secrets.token_urlsafe(32))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(db: Session, user: User) -> str:
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= utcnow()))
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(token), expires_at=utcnow() + SESSION_TTL))
    return token


def set_session_cookie(response, request: Request, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=request.app.state.secure_cookies,
        samesite="strict",
        path="/",
    )


def _session_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token or len(token) > 128:
        return None
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_digest(token),
            AuthSession.expires_at > utcnow(),
        )
    )
    if not session:
        return None
    user = db.get(User, session.user_id)
    return user if user and user.is_active else None


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return _session_user(request, db)


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "سجّل الدخول للمتابعة")
    return user


def get_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "هذه العملية للمشرفين فقط")
    return user