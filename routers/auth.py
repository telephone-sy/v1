import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import (
    SESSION_COOKIE,
    enforce_rate_limit,
    DUMMY_PASSWORD_HASH,
    get_current_user,
    get_optional_user,
    issue_session,
    password_hash,
    set_session_cookie,
    token_digest,
)
from database import get_db
from models import AuthSession, User
from schemas import LoginIn, RegisterIn, UserOut


router = APIRouter(prefix="/api/auth", tags=["المصادقة"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "register", 5, 3600, identity=payload.phone)
    if db.scalar(select(User).where(User.phone == payload.phone)):
        raise HTTPException(status.HTTP_409_CONFLICT, "رقم الهاتف مسجل مسبقاً")
    user = User(
        name=payload.name.strip(),
        phone=payload.phone,
        password_hash=password_hash.hash(payload.password),
        shop=payload.shop,
        city=payload.city,
        region=payload.region,
    )
    db.add(user)
    try:
        db.flush()
        token = issue_session(db, user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "رقم الهاتف مسجل مسبقاً") from None
    db.refresh(user)
    set_session_cookie(response, request, token)
    logger.info("user_registered user_id=%s", user.id)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "login", 8, identity=payload.phone)
    user = db.scalar(select(User).where(User.phone == payload.phone))
    password_ok = password_hash.verify(payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not user.is_active or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "رقم الهاتف أو كلمة المرور غير صحيحة")
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(old_token)))
    token = issue_session(db, user)
    db.commit()
    set_session_cookie(response, request, token)
    logger.info("user_login user_id=%s", user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=request.app.state.secure_cookies, httponly=True, samesite="strict")


@router.get("/me", response_model=UserOut | None)
def me(user: User | None = Depends(get_optional_user)):
    return user

