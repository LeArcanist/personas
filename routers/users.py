from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

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
    # 1️⃣ Check if username or email already exists
    existing_user = db.query(models.User).filter(
        (models.User.username == username) |
        (models.User.email == email)
    ).first()

    if existing_user:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Username or email already exists"
            }
        )

    # 2️⃣ Hash the password
    hashed_pw = hash_password(password)

    # 3️⃣ Create User ORM object
    new_user = models.User(
        username=username,
        email=email,
        password_hash=hashed_pw
    )

    # 4️⃣ Save to database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)  # gets generated ID

    # 5️⃣ Return success message
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "success": f"Account created successfully for {new_user.username}"
        }
    )

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
