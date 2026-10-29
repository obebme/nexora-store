import sys
from getpass import getpass

from sqlalchemy import select

from .database import SessionLocal
from .models import User
from .security import hash_password


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Использование: python -m nexora_backend.create_admin EMAIL")
    email = sys.argv[1].strip().lower()
    password = getpass("Новый пароль администратора (от 14 символов): ")
    if len(password) < 14:
        raise SystemExit("Пароль должен содержать не менее 14 символов.")
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash=hash_password(password), role="admin")
            db.add(user)
        else:
            user.password_hash = hash_password(password)
            user.role = "admin"
            user.is_active = True
    print(f"Администратор настроен: {email}")


if __name__ == "__main__":
    main()
