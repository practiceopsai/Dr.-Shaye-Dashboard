"""Public, synthetic voice preview for a Twilio trial call.

This route serves only the bundled introduction. It does not authenticate a
caller, accept a request for Eli, read private context, or invoke any AI API.
"""

import os
import re
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response


router = APIRouter(prefix="/api/phone", tags=["Phone preview"])
PREVIEW_AUDIO = Path(__file__).with_name("assets") / "eli-marin-preview.mp3"
PREVIEW_AUDIO_VERSION = "marin-20260920"


@router.get("/preview")
@router.post("/preview")
def preview_instructions() -> Response:
    # Railway supplies the service's own public domain. Never construct the
    # audio destination from an untrusted Host or forwarded-host header.
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", domain):
        raise HTTPException(status_code=503, detail="Phone preview is not configured")
    if not PREVIEW_AUDIO.is_file():
        raise HTTPException(status_code=503, detail="Phone preview audio is unavailable")
    root = Element("Response")
    # Change the audio URL with the voice so callers do not hear a cached preview.
    SubElement(root, "Play").text = (
        f"https://{domain}/api/phone/preview.mp3?v={PREVIEW_AUDIO_VERSION}"
    )
    SubElement(root, "Hangup")
    return Response(
        tostring(root, encoding="unicode"),
        media_type="application/xml",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/preview.mp3")
def preview_audio() -> FileResponse:
    if not PREVIEW_AUDIO.is_file():
        raise HTTPException(status_code=503, detail="Phone preview audio is unavailable")
    return FileResponse(PREVIEW_AUDIO, media_type="audio/mpeg")
