"""ORM models owned by the auth module. No other module may query these tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.auth.constants import AuthLimits, UserRole, UserStatus


class Department(Base):
    """A department synced from DX, used for role/onboarding decisions."""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(AuthLimits.MAX_NAME_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    """A user account, synced from a DX profile on every successful login."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(AuthLimits.MAX_EMAIL_LENGTH), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(AuthLimits.MAX_NAME_LENGTH))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), default=UserRole.MEMBER)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False), default=UserStatus.PENDING, index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    employee_code: Mapped[str | None] = mapped_column(
        String(AuthLimits.MAX_EMPLOYEE_CODE_LENGTH), nullable=True
    )
    email_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    department: Mapped["Department | None"] = relationship(lazy="joined")
