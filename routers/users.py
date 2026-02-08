from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# mfa
import io
import base64
import pyotp
import qrcode

from database import SessionLocal
import models
from auth_utils import hash_password, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/mfa/setup", response_class=HTMLResponse)
def mfa_setup(request: Request, db: Session = Depends(get_db)):
    user_id = require_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)

    # If user doesn't have a secret yet, generate one
    if not user.totp_secret:
        user.totp_secret = pyotp.random_base32()
        db.commit()
        db.refresh(user)

    issuer = "ContextIdentityFYP"  # shows up in Google Authenticator
    totp = pyotp.TOTP(user.totp_secret)

    # otpauth URI Google Authenticator understands
    otpauth_uri = totp.provisioning_uri(name=user.username, issuer_name=issuer)

    # Generate QR code PNG in memory and base64 encode for HTML <img>
    img = qrcode.make(otpauth_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return templates.TemplateResponse(
        "mfa_setup.html",
        {
            "request": request,
            "username": user.username,
            "qr_b64": qr_b64,
            "secret": user.totp_secret, 
            "already_enabled": bool(user.mfa_enabled),
        }
    )

@router.post("/mfa/confirm", response_class=HTMLResponse)
def mfa_confirm(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    user_id = require_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.totp_secret:
        return RedirectResponse(url="/mfa/setup", status_code=303)

    totp = pyotp.TOTP(user.totp_secret)

    # valid_window=1 tolerates small clock drift
    if not totp.verify(code.strip(), valid_window=1):
        return templates.TemplateResponse(
            "mfa_setup.html",
            {
                "request": request,
                "username": user.username,
                "error": "Invalid code. Try again.",
                "qr_b64": None, 
                "secret": user.totp_secret,
                "already_enabled": bool(user.mfa_enabled),
            }
        )

    user.mfa_enabled = True
    db.commit()

    return RedirectResponse(url="/mfa/setup", status_code=303)

@router.get("/mfa/verify", response_class=HTMLResponse)
def mfa_verify_form(request: Request):
    pending = request.session.get("mfa_pending_user_id")
    if not pending:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse("mfa_verify.html", {"request": request})

@router.post("/mfa/verify", response_class=HTMLResponse)
def mfa_verify_submit(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    pending_user_id = request.session.get("mfa_pending_user_id")
    if not pending_user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(models.User).filter(models.User.id == pending_user_id).first()
    if not user or not user.mfa_enabled or not user.totp_secret:
        request.session.pop("mfa_pending_user_id", None)
        return RedirectResponse(url="/login", status_code=303)

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code.strip(), valid_window=1):
        return templates.TemplateResponse(
            "mfa_verify.html",
            {"request": request, "error": "Invalid code. Try again."}
        )

    request.session.pop("mfa_pending_user_id", None)
    request.session["user_id"] = user.id
    request.session["username"] = user.username

    return RedirectResponse(url="/dashboard", status_code=303)


def require_user_id(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return user_id

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

@router.post("/login", response_class=HTMLResponse)
def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.username == username
    ).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid username or password"
            }
        )
    
    request.session.clear()

    if user.mfa_enabled:
        request.session["mfa_pending_user_id"] = user.id
        return RedirectResponse(url="/mfa/verify", status_code=303)

    request.session["user_id"] = user.id
    request.session["username"] = user.username
    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request}
    )

@router.post("/register", response_class=HTMLResponse)
def register_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    username = username.strip()
    email = email.strip().lower()

    user = models.User(
        username=username,
        email=email,
        password_hash=hash_password(password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Optional: auto-login after register
    request.session["user_id"] = user.id
    request.session["username"] = user.username

    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    personas = db.query(models.Persona).filter(models.Persona.user_id == user_id).all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "personas": personas
        }
    )

@router.get("/personas/new", response_class=HTMLResponse)
def new_persona_form(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse("persona_new.html", {"request": request})

@router.get("/personas/{persona_id}/edit", response_class=HTMLResponse)
def edit_persona_form(persona_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()

    # Security: ensure persona belongs to logged in user
    if not persona or persona.user_id != user_id:
        return RedirectResponse(url="/dashboard", status_code=303)

    return templates.TemplateResponse(
        "persona_edit.html",
        {"request": request, "persona": persona}
    )

@router.post("/personas/{persona_id}/edit", response_class=HTMLResponse)
def edit_persona_save(
    persona_id: int,
    request: Request,
    category: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    is_public: str = Form("0"),
    db: Session = Depends(get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona or persona.user_id != user_id:
        return RedirectResponse(url="/dashboard", status_code=303)

    # Optional: prevent duplicate names per user (if they rename)
    duplicate = db.query(models.Persona).filter(
        models.Persona.user_id == user_id,
        models.Persona.name == name,
        models.Persona.id != persona_id
    ).first()
    if duplicate:
        return templates.TemplateResponse(
            "persona_edit.html",
            {"request": request, "persona": persona, "error": "You already have a profile with that name."}
        )

    persona.category = category
    persona.name = name
    persona.description = description.strip() if description else None
    persona.is_public = True if is_public == "1" else False

    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/personas/{persona_id}", response_class=HTMLResponse)
def view_persona(persona_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona or persona.user_id != user_id:
        return RedirectResponse(url="/dashboard", status_code=303)
    others = (
        db.query(models.Persona, models.User.username)
        .join(models.User, models.User.id == models.Persona.user_id)
        .filter(models.Persona.category == persona.category)
        .filter(models.Persona.is_public == True)
        .filter(models.Persona.user_id != user_id)
        .all()
    )

    others_clean = []
    for p, owner_username in others:
        others_clean.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "owner_username": owner_username
        })

    return templates.TemplateResponse(
        "persona_view.html",
        {
            "request": request,
            "persona": persona,
            "others": others_clean
        }
    )

@router.get("/public/{username}/{persona_id}", response_class=HTMLResponse)
def view_public_persona(username: str, persona_id: int, request: Request, db: Session = Depends(get_db)):
    persona = (
        db.query(models.Persona)
        .join(models.User, models.User.id == models.Persona.user_id)
        .filter(models.User.username == username)
        .filter(models.Persona.id == persona_id)
        .filter(models.Persona.is_public == True)
        .first()
    )

    if not persona:
        return templates.TemplateResponse(
            "persona_public.html",
            {"request": request, "error": "Public profile not found."}
        )

    return templates.TemplateResponse(
        "persona_public.html",
        {"request": request, "persona": persona}
    )


@router.post("/personas/new", response_class=HTMLResponse)
def create_persona(
    request: Request,
    category: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    is_public: str = Form("0"),
    db: Session = Depends(get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    
    existing = db.query(models.Persona).filter(
        models.Persona.user_id == user_id,
        models.Persona.name == name
    ).first()
    if existing:
        return templates.TemplateResponse(
            "persona_new.html",
            {"request": request, "error": "You already have a profile with that name."}
        )

    persona = models.Persona(
        user_id=user_id,
        name=name,
        category=category,
        description=description.strip() if description else None,
        is_public=(is_public == "1")
    )

    db.add(persona)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)
