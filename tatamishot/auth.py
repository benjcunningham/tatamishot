from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, HTTPException


PLEX_TV_URL = "https://plex.tv"
CLIENT_ID = uuid.uuid4().hex

_HEADERS = {
    "X-Plex-Product": "TatamiShot",
    "X-Plex-Client-Identifier": CLIENT_ID,
    "Accept": "application/json",
}

router = APIRouter(prefix="/auth")


@router.post("/pin")
async def create_pin() -> dict[str, str]:
    """Start a Plex PIN-based auth flow. Returns the pin_id, code, and auth URL."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{PLEX_TV_URL}/api/v2/pins",
                headers=_HEADERS,
                params={"strong": "true"},
                timeout=10,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Plex unreachable: {exc}") from exc

    data = resp.json()
    pin_id = str(data["id"])
    code = data["code"]
    auth_url = f"https://app.plex.tv/auth#?clientID={CLIENT_ID}&code={code}&context[device][product]=TatamiShot"

    return {"pin_id": pin_id, "code": code, "auth_url": auth_url}


@router.get("/pin/{pin_id}")
async def poll_pin(pin_id: int) -> dict[str, str | None]:
    """Poll a Plex PIN for completion. Returns auth_token when the user authorizes."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{PLEX_TV_URL}/api/v2/pins/{pin_id}",
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Plex unreachable: {exc}") from exc

    data = resp.json()
    return {"auth_token": data.get("authToken")}
