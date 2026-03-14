from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from security.oauth import oauth

router = APIRouter()

@router.get("/login/google")
async def login_google(request: Request):
    redirect_uri = request.url_for("auth_google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/auth/google/callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token["userinfo"]

    provider = "google"
    provider_user_id = user_info["sub"]

    identity = (
        db.query(models.ExternalIdentity)
        .filter(models.ExternalIdentity.provider == provider)
        .filter(models.ExternalIdentity.provider_user_id == provider_user_id)
        .first()
    )

    if identity:
        user = db.query(models.User).filter(models.User.id == identity.user_id).first()
    else:
        email = user_info.get("email")
        name = user_info.get("name") or email.split("@")[0]
        base_username = (user_info.get("name") or email.split("@")[0]).replace(" ", "_")

        user = models.User(
            username=base_username,
            email=email,
            password_hash="GOOGLE_OAUTH_NO_LOCAL_PASSWORD"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        identity = models.ExternalIdentity(
            persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False),
            provider=provider,
            provider_user_id=provider_user_id,
            email=user_info.get("email"),
            name=user_info.get("name"),
            picture=user_info.get("picture")
        )

        db.add(identity)
        db.commit()

    request.session["user_id"] = user.id

    return RedirectResponse("/dashboard")