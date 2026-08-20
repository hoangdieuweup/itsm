"""ORM model owned by the dx_core integration. No other module may query this table.

Structural skeleton: the columns exist so the SSO integration sub-issue has a
place to write encrypted tokens into, but nothing writes to this table yet —
the Fernet encryption in app.core.crypto is out of scope for this issue (see
issue #3's "Not owned by this issue" section). access_token/refresh_token
store ciphertext (base64), never plaintext, once that lands.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DxToken(Base):
    """Encrypted WeUpBook DX token set for one user, one row per user."""

    __tablename__ = "dx_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
