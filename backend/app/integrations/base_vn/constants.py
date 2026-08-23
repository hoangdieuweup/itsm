from enum import StrEnum


class BaseVnErrorCode(StrEnum):
    UNAVAILABLE = "base_vn_unavailable"
    REJECTED = "base_vn_rejected"
