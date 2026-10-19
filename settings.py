import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


@dataclass(frozen=True)
class Settings:
    environment: str
    allowed_hosts: tuple[str, ...]
    redis_url: str | None
    database_url: str
    upload_dir: Path
    max_request_bytes: int

    @property
    def production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_environment(cls) -> "Settings":
        environment = os.getenv("ENVIRONMENT", "development").strip().lower()
        if environment not in {"development", "production", "test"}:
            raise RuntimeError("ENVIRONMENT must be development, test, or production")
        configured_hosts = os.getenv("ALLOWED_HOSTS")
        if environment == "production" and not configured_hosts:
            raise RuntimeError("ALLOWED_HOSTS must be explicitly configured in production")
        hosts = tuple(host.strip() for host in (configured_hosts or "localhost,127.0.0.1,testserver").split(",") if host.strip())
        if not hosts or "*" in hosts:
            raise RuntimeError("ALLOWED_HOSTS must contain explicit hostnames and must not contain '*'")
        redis_url = os.getenv("REDIS_URL") or None
        if environment == "production":
            if not redis_url:
                raise RuntimeError("REDIS_URL is required in production for shared rate limits")
            if urlsplit(redis_url).scheme != "rediss":
                raise RuntimeError("REDIS_URL must use TLS (rediss://) in production")
            if not urlsplit(redis_url).password:
                raise RuntimeError("REDIS_URL must authenticate with a password in production")
            if "testserver" in hosts:
                raise RuntimeError("Remove testserver from production ALLOWED_HOSTS")
        database_url = os.getenv("DATABASE_URL", "sqlite:///./telephone_sy.db")
        if environment == "production":
            database_parts = urlsplit(database_url)
            sslmode = parse_qs(database_parts.query).get("sslmode", [""])[0]
            if database_parts.scheme != "postgresql+psycopg" or not database_parts.password:
                raise RuntimeError("Production DATABASE_URL must use authenticated PostgreSQL with psycopg")
            if sslmode != "verify-full":
                raise RuntimeError("Production DATABASE_URL must verify TLS certificates and hostname via sslmode=verify-full")
        max_request_bytes = int(os.getenv("MAX_REQUEST_BYTES", str(30 * 1024 * 1024)))
        if not 1024 * 1024 <= max_request_bytes <= 100 * 1024 * 1024:
            raise RuntimeError("MAX_REQUEST_BYTES must be between 1 and 100 MiB")
        return cls(
            environment=environment,
            allowed_hosts=hosts,
            redis_url=redis_url,
            database_url=database_url,
            upload_dir=Path(os.getenv("UPLOAD_DIR", "./uploads")).resolve(),
            max_request_bytes=max_request_bytes,
        )