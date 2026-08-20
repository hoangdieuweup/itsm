"""JWT session token mechanism shared by any module that issues sessions.

Generic on purpose: no secret or TTL is hardcoded here, and no module
specific error is raised — a module (see app/modules/auth/config.py and
app/modules/auth/services/issue_tokens.py) supplies its own secret/TTL and
maps jwt.PyJWTError to its own AppError subclass, keeping "core holds
mechanism, never a business concept" intact.
"""

import time
from typing import Any

import jwt


class JwtCodec:
    """Encode/decode short-lived claims with HS256. Stateless, no I/O."""

    ALGORITHM = "HS256"

    @staticmethod
    def encode(claims: dict[str, Any], *, secret: str, ttl_seconds: int) -> str:
        """Sign claims into a token that expires ttl_seconds from now."""
        now = int(time.time())
        payload = {**claims, "iat": now, "exp": now + ttl_seconds}
        return jwt.encode(payload, secret, algorithm=JwtCodec.ALGORITHM)

    @staticmethod
    def decode(token: str, *, secret: str) -> dict[str, Any]:
        """Verify signature and expiry, returning the claims.

        Raises jwt.PyJWTError (or a subclass, e.g. ExpiredSignatureError,
        InvalidSignatureError) on any failure — the caller maps that to its
        own domain error, since core has no ErrorCode of its own to raise.
        """
        return jwt.decode(token, secret, algorithms=[JwtCodec.ALGORITHM])
