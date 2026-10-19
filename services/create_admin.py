from getpass import getpass

from dotenv import load_dotenv
from sqlalchemy import delete, select

load_dotenv()

from auth import password_hash
from database import SessionLocal
from models import AuthSession, User


def ensure_admin(db, phone: str, name: str, password: str) -> None:
    user = db.scalar(select(User).where(User.phone == phone))
    if user:
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        user.name = name
        user.password_hash = password_hash.hash(password)
        user.role = "admin"
        user.is_active = True
    else:
        db.add(User(name=name, phone=phone, password_hash=password_hash.hash(password), role="admin"))


def main() -> None:
    phone = input("Admin phone (09xxxxxxxx): ").strip()
    if len(phone) != 10 or not phone.startswith("09") or not phone.isdigit():
        raise SystemExit("Invalid Syrian phone number")
    name = input("Admin display name: ").strip()
    if not name or len(name) > 120:
        raise SystemExit("Name must be between 1 and 120 characters")
    password = getpass("Admin password (10+ characters): ")
    if len(password) < 10:
        raise SystemExit("Password must be at least 10 characters")

    with SessionLocal() as db:
        ensure_admin(db, phone, name, password)
        db.commit()
    print("Admin account ready. Keep its credentials private.")


if __name__ == "__main__":
    main()