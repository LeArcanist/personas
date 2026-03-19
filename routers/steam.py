from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
import models

import requests
import re

router = APIRouter()

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"

STEAM_API_KEY = "D49B7E29AB926DE532FB61B037FD4B37" 


@router.get("/personas/{persona_id}/link/steam")
def link_steam(request: Request, persona_id: int):
    request.session["link_persona_id"] = persona_id

    redirect_uri = str(request.url_for("steam_callback"))

    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": redirect_uri,
        "openid.realm": redirect_uri,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }

    query = "&".join([f"{k}={v}" for k, v in params.items()])

    return RedirectResponse(f"{STEAM_OPENID_URL}?{query}")

@router.get("/auth/steam/callback", name="steam_callback")
def steam_callback(request: Request, db: Session = Depends(get_db)):
    persona_id = request.session.get("link_persona_id")
    user_id = request.session.get("user_id")

    if not persona_id or not user_id:
        return RedirectResponse("/dashboard", status_code=303)

    # Get SteamID from OpenID response
    claimed_id = request.query_params.get("openid.claimed_id")

    match = re.search(r"/id/(\d+)$", claimed_id or "")
    if not match:
        match = re.search(r"/(\d+)$", claimed_id or "")

    if not match:
        return RedirectResponse("/dashboard", status_code=303)

    steam_id = match.group(1)

    # Fetch profile from Steam API
    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
    data = requests.get(url).json()

    players = data.get("response", {}).get("players", [])
    profile = players[0] if players else {}

    # Save identity
    identity = models.ExternalIdentity(
        persona_id=persona_id,
        provider="steam",
        provider_user_id=steam_id,
        name=profile.get("personaname"),
        picture=profile.get("avatarfull"),
    )

    db.add(identity)
    db.commit()

    request.session.pop("link_persona_id", None)

    return RedirectResponse(f"/personas/{persona_id}", status_code=303)