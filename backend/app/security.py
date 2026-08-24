import hashlib
import json
import re
from dataclasses import dataclass
from fastapi import Header, HTTPException
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token as google_id_token
from .config import get_settings


PHI_PATTERNS = [
    r"\bmrn\b", r"medical record number", r"\bdob\s*[:#]", r"date of birth",
    r"patient\s+[a-z]+\s+[a-z]+", r"\bdiagnos(?:is|ed|es)\b", r"\bicd-?10\b",
    r"pathology report", r"lab result",
]


@dataclass(frozen=True)
class AuthUser:
    subject: str
    email: str
    name: str
    picture: str | None = None

    @property
    def role(self) -> str:
        return "owner" if self.email == "oshaye@gastrobh.com" else "chief_of_staff"


def verify_google_credential(credential: str) -> AuthUser:
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        claims = google_id_token.verify_oauth2_token(
            credential,
            Request(),
            settings.google_client_id,
        )
    except (ValueError, GoogleAuthError):
        raise HTTPException(status_code=401, detail="Google sign-in has expired or is invalid") from None

    email = str(claims.get("email") or "").strip().lower()
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    hosted_domain = str(claims.get("hd") or "").strip().lower()
    if (
        not claims.get("sub")
        or claims.get("email_verified") is not True
        or email not in settings.allowed_google_emails
        or not hosted_domain
        or hosted_domain != domain
    ):
        raise HTTPException(status_code=403, detail="This Google account is not authorized for Eli Command Center")

    return AuthUser(
        subject=str(claims["sub"]),
        email=email,
        name=str(claims.get("name") or email),
        picture=str(claims["picture"]) if claims.get("picture") else None,
    )


def require_auth(authorization: str | None = Header(default=None)) -> AuthUser:
    scheme, separator, credential = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "bearer" or not credential.strip():
        raise HTTPException(status_code=401, detail="Google sign-in is required")
    return verify_google_credential(credential.strip())


def contains_phi(text: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in PHI_PATTERNS)


def payload_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
