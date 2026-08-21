import hashlib
import hmac
import json
import re
from fastapi import Header, HTTPException
from .config import get_settings


PHI_PATTERNS = [
    r"\bmrn\b", r"medical record number", r"\bdob\s*[:#]", r"date of birth",
    r"patient\s+[a-z]+\s+[a-z]+", r"\bdiagnos(?:is|ed|es)\b", r"\bicd-?10\b",
    r"pathology report", r"lab result",
]


def require_auth(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().dashboard_access_token
    if not expected:
        raise HTTPException(status_code=503, detail="Dashboard access token is not configured")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid access token")


def contains_phi(text: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in PHI_PATTERNS)


def payload_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

