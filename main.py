import logging
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from database import Base, engine, get_db
import models
from routers import admin, auth, favorites, listings, reports, users
from security_middleware import RequestBodyLimitMiddleware
from settings import Settings


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = Settings.from_environment()
UPLOAD_DIR = settings.upload_dir
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not settings.production:
        Base.metadata.create_all(bind=engine)
    redis_client = None
    if settings.redis_url:
        redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
        await asyncio.to_thread(redis_client.ping)
    _app.state.redis = redis_client
    try:
        yield
    finally:
        if redis_client is not None:
            redis_client.close()


app = FastAPI(
    title="telephone-sy API",
    description="واجهات سوق الهاتف السوري. الأسعار تعرض بعملة الإعلان دون تحويل.",
    version="1.0.0",
    docs_url=None if settings.production else "/docs",
    redoc_url=None if settings.production else "/redoc",
    openapi_url=None if settings.production else "/openapi.json",
    lifespan=lifespan,
)
app.state.secure_cookies = settings.production
app.state.redis = None
app.add_middleware(RequestBodyLimitMiddleware, maximum_bytes=settings.max_request_bytes)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=str(Path(__file__).with_name("static"))), name="static")
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(listings.router)
app.include_router(favorites.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.middleware("http")
async def same_origin_mutations(request, call_next):
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse(status_code=403, content={"detail": "مصدر الطلب غير مسموح"})
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
        parsed = urlsplit(origin)
        if parsed.netloc != request.headers.get("host") or parsed.scheme not in {"http", "https"}:
            return JSONResponse(status_code=403, content={"detail": "مصدر الطلب غير مسموح"})
    return await call_next(request)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' data: blob:; script-src 'self'; "
        "style-src 'self'; style-src-attr 'none'; connect-src 'self'; upgrade-insecure-requests"
        if settings.production else
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' data: blob:; script-src 'self'; "
        "style-src 'self'; style-src-attr 'none'; connect-src 'self'"
    )
    if settings.production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz", tags=["النظام"])
def health():
    return {"status": "ok"}


@app.get("/readyz", tags=["النظام"])
def readiness(db=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        if settings.production:
            app.state.redis.ping()
    except (SQLAlchemyError, RedisError, AttributeError, OSError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "الخدمة غير جاهزة") from None
    return {"status": "ready"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).with_name("index.html"))