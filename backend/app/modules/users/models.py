"""ORM models owned by the users module. No other module may query these tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.users.constants import UserLimits, UserStatus


class User(Base):
    """A user account, synced from a DX profile on every successful login."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(UserLimits.MAX_EMAIL_LENGTH), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(UserLimits.MAX_NAME_LENGTH))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False), default=UserStatus.PENDING, index=True
    )
    external_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    employee_code: Mapped[str | None] = mapped_column(
        String(UserLimits.MAX_EMPLOYEE_CODE_LENGTH), nullable=True
    )
    email_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
