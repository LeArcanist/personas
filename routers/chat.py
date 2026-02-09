from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from fastapi.responses import JSONResponse
from sqlalchemy import func
from datetime import datetime

import models
from database import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/chats", response_class=HTMLResponse)
def chats_home(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # Load user's personas 
    personas = (
        db.query(models.Persona)
        .filter(models.Persona.user_id == user_id)
        .order_by(models.Persona.category.asc(), models.Persona.name.asc())
        .all()
    )

    # Build categories list + serialize personas
    categories = sorted({(p.category or "other") for p in personas})

    personas_data = [
        {
            "id": p.id,
            "name": p.name,
            "category": (p.category or "other"),
            "is_public": bool(getattr(p, "is_public", False)),
        }
        for p in personas
    ]

    active_persona_id = request.session.get("active_persona_id")

    return templates.TemplateResponse(
        "chats_home.html",
        {
            "request": request,
            "categories": categories,
            "personas": personas_data,
            "active_persona_id": active_persona_id,
        }
    )

@router.post("/chats/enter")
def chats_enter(
    request: Request,
    category: str = Form(...),
    persona_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    category = category.strip().lower()

    # Security check: ensure persona belongs to the user AND matches chosen category
    persona = (
        db.query(models.Persona)
        .filter(models.Persona.id == persona_id)
        .first()
    )

    if not persona or persona.user_id != user_id:
        return RedirectResponse(url="/chats", status_code=303)

    if (persona.category or "other").strip().lower() != category:
        return RedirectResponse(url="/chats", status_code=303)


    request.session["active_persona_id"] = persona.id
    request.session["active_category"] = category  

    return RedirectResponse(url=f"/chats/{category}", status_code=303)

def get_active_persona_for_category(request: Request, db: Session, category: str):
    user_id = request.session.get("user_id")
    if not user_id:
        return None, None

    active_persona_id = request.session.get("active_persona_id")
    if not active_persona_id:
        return user_id, None

    persona = db.query(models.Persona).filter(models.Persona.id == active_persona_id).first()
    if not persona or persona.user_id != user_id:
        return user_id, None

    if (persona.category or "other").strip().lower() != category.strip().lower():
        return user_id, None

    return user_id, persona

@router.get("/chats/{category}", response_class=HTMLResponse)
def chats_room(category: str, request: Request, db: Session = Depends(get_db)):
    user_id, active_persona = get_active_persona_for_category(request, db, category)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    if not active_persona:
        return RedirectResponse(url="/chats", status_code=303)

    category_norm = category.strip().lower()

    rows = (
        db.query(models.CategoryMessage, models.Persona.name)
        .join(models.Persona, models.Persona.id == models.CategoryMessage.sender_persona_id)
        .filter(models.CategoryMessage.category == category_norm)
        .order_by(models.CategoryMessage.id.desc())
        .limit(50)
        .all()
    )
    rows.reverse()

    messages = [{
        "id": m.id,
        "sender_name": sender_name,
        "content": m.content,
        "created_at": m.created_at.isoformat(timespec="seconds"),
        "is_me": (m.sender_persona_id == active_persona.id),
    } for m, sender_name in rows]

    people = (
    db.query(models.Persona)
    .filter(models.Persona.category == category_norm)
    .filter(models.Persona.is_public.is_(True))
    .filter(models.Persona.id != active_persona.id)
    .order_by(models.Persona.name.asc())
    .limit(50)
    .all()
    )

    people_data = [
        {"id": p.id, "name": p.name, "description": p.description}
        for p in people
    ]

    return templates.TemplateResponse(
        "chat_room.html",
        {
            "request": request,
            "category": category_norm,
            "active_persona": {"id": active_persona.id, "name": active_persona.name},
            "messages": messages,
            "people": people_data,
        }
    )

@router.post("/chats/{category}/send")
def chats_send(category: str, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user_id, active_persona = get_active_persona_for_category(request, db, category)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    if not active_persona:
        return RedirectResponse(url="/chats", status_code=303)

    text = content.strip()
    if not text:
        return RedirectResponse(url=f"/chats/{category}", status_code=303)

    # anti-spam constraint
    if len(text) > 500:
        text = text[:500]

    msg = models.CategoryMessage(
        category=category.strip().lower(),
        sender_persona_id=active_persona.id,
        content=text,
    )
    db.add(msg)
    db.commit()

    return RedirectResponse(url=f"/chats/{category.strip().lower()}", status_code=303)

@router.get("/chats/{category}/messages")
def chats_messages(category: str, request: Request, after_id: int = 0, db: Session = Depends(get_db)):
    user_id, active_persona = get_active_persona_for_category(request, db, category)
    if not user_id:
        return JSONResponse({"error": "not_logged_in"}, status_code=401)
    if not active_persona:
        return JSONResponse({"error": "no_active_persona"}, status_code=403)

    category_norm = category.strip().lower()

    rows = (
        db.query(models.CategoryMessage, models.Persona.name)
        .join(models.Persona, models.Persona.id == models.CategoryMessage.sender_persona_id)
        .filter(models.CategoryMessage.category == category_norm)
        .filter(models.CategoryMessage.id > after_id)
        .order_by(models.CategoryMessage.id.asc())
        .limit(100)
        .all()
    )

    payload = [{
        "id": m.id,
        "sender_name": sender_name,
        "content": m.content,
        "created_at": m.created_at.isoformat(timespec="seconds"),
        "is_me": (m.sender_persona_id == active_persona.id),
    } for m, sender_name in rows]

    return JSONResponse(payload)

@router.post("/dm/start")
def dm_start(
    request: Request,
    target_persona_id: int = Form(...),
    db: Session = Depends(get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    active_persona_id = request.session.get("active_persona_id")
    if not active_persona_id:
        return RedirectResponse(url="/chats", status_code=303)

    active = db.query(models.Persona).filter(models.Persona.id == active_persona_id).first()
    target = db.query(models.Persona).filter(models.Persona.id == target_persona_id).first()

    if not active or active.user_id != user_id:
        return RedirectResponse(url="/chats", status_code=303)

    if not target or not getattr(target, "is_public", False):
        return RedirectResponse(url=f"/chats/{(active.category or 'other').strip().lower()}", status_code=303)

    # Context-specific rule: only DM within same category
    cat_a = (active.category or "other").strip().lower()
    cat_b = (target.category or "other").strip().lower()
    if cat_a != cat_b:
        return RedirectResponse(url=f"/chats/{cat_a}", status_code=303)

    # Prevent DM with yourself
    if active.id == target.id:
        return RedirectResponse(url=f"/chats/{cat_a}", status_code=303)

    # Reuse existing thread regardless of ordering
    existing = (
        db.query(models.DMThread)
        .filter(models.DMThread.category == cat_a)
        .filter(
            ((models.DMThread.persona_a_id == active.id) & (models.DMThread.persona_b_id == target.id)) |
            ((models.DMThread.persona_a_id == target.id) & (models.DMThread.persona_b_id == active.id))
        )
        .first()
    )

    if existing:
        return RedirectResponse(url=f"/dm/{existing.id}", status_code=303)

    thread = models.DMThread(
        persona_a_id=active.id,
        persona_b_id=target.id,
        category=cat_a
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)

    return RedirectResponse(url=f"/dm/{thread.id}", status_code=303)

@router.get("/dm/{thread_id}", response_class=HTMLResponse)
def dm_thread(thread_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    active_persona_id = request.session.get("active_persona_id")
    if not active_persona_id:
        return RedirectResponse(url="/chats", status_code=303)

    thread = db.query(models.DMThread).filter(models.DMThread.id == thread_id).first()
    if not thread:
        return RedirectResponse(url="/dm", status_code=303)

    # must be participant
    if active_persona_id not in (thread.persona_a_id, thread.persona_b_id):
        return RedirectResponse(url="/dm", status_code=303)

    active = db.query(models.Persona).filter(models.Persona.id == active_persona_id).first()
    if not active or active.user_id != user_id:
        return RedirectResponse(url="/chats", status_code=303)

    other_id = thread.persona_b_id if active_persona_id == thread.persona_a_id else thread.persona_a_id
    other = db.query(models.Persona).filter(models.Persona.id == other_id).first()

    rows = (
        db.query(models.DMMessage, models.Persona.name)
        .join(models.Persona, models.Persona.id == models.DMMessage.sender_persona_id)
        .filter(models.DMMessage.thread_id == thread.id)
        .order_by(models.DMMessage.id.desc())
        .limit(50)
        .all()
    )
    rows.reverse()

    messages = [{
        "id": m.id,
        "sender_name": sender_name,
        "content": m.content,
        "created_at": m.created_at.isoformat(timespec="seconds"),
        "is_me": (m.sender_persona_id == active.id),
    } for m, sender_name in rows]

    return templates.TemplateResponse(
        "dm_thread.html",
        {
            "request": request,
            "thread_id": thread.id,
            "category": thread.category,
            "active_persona": {"id": active.id, "name": active.name},  # ✅ now defined
            "other_name": other.name if other else "Unknown",
            "messages": messages,
        }
    )


def require_active_persona(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None, None

    active_persona_id = request.session.get("active_persona_id")
    if not active_persona_id:
        return user_id, None

    persona = db.query(models.Persona).filter(models.Persona.id == active_persona_id).first()
    if not persona or persona.user_id != user_id:
        return user_id, None

    return user_id, persona

@router.get("/dm", response_class=HTMLResponse)
def dm_inbox(request: Request, db: Session = Depends(get_db)):
    user_id, active = require_active_persona(request, db)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    if not active:
        return RedirectResponse(url="/chats", status_code=303)

    threads = (
        db.query(models.DMThread)
        .filter(
            (models.DMThread.persona_a_id == active.id) |
            (models.DMThread.persona_b_id == active.id)
        )
        .order_by(models.DMThread.id.desc())
        .limit(50)
        .all()
    )

    items = []
    for t in threads:
        other_id = t.persona_b_id if t.persona_a_id == active.id else t.persona_a_id
        other = db.query(models.Persona).filter(models.Persona.id == other_id).first()

        items.append({
            "thread_id": t.id,
            "category": t.category,
            "other_name": other.name if other else "Unknown",
        })

    return templates.TemplateResponse(
        "dm_inbox.html",
        {"request": request, "active_persona": active.name, "threads": items}
    )

@router.get("/dm/{thread_id}", response_class=HTMLResponse)
def dm_thread(thread_id: int, request: Request, db: Session = Depends(get_db)):
    user_id, active = require_active_persona(request, db)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    if not active:
        return RedirectResponse(url="/chats", status_code=303)

    thread = db.query(models.DMThread).filter(models.DMThread.id == thread_id).first()
    if not thread:
        return RedirectResponse(url="/dm", status_code=303)

    if active.id not in (thread.persona_a_id, thread.persona_b_id):
        return RedirectResponse(url="/dm", status_code=303)

    other_id = thread.persona_b_id if active.id == thread.persona_a_id else thread.persona_a_id
    other = db.query(models.Persona).filter(models.Persona.id == other_id).first()

    rows = (
        db.query(models.DMMessage, models.Persona.name)
        .join(models.Persona, models.Persona.id == models.DMMessage.sender_persona_id)
        .filter(models.DMMessage.thread_id == thread.id)
        .order_by(models.DMMessage.id.desc())
        .limit(50)
        .all()
    )
    rows.reverse()

    messages = [{
        "id": m.id,
        "sender_name": sender_name,
        "content": m.content,
        "created_at": m.created_at.isoformat(timespec="seconds"),
        "is_me": (m.sender_persona_id == active.id),
    } for m, sender_name in rows]

    return templates.TemplateResponse(
        "dm_thread.html",
        {
            "request": request,
            "thread_id": thread.id,
            "category": thread.category,
            "active_persona": {"id": active.id, "name": active.name},
            "other_name": other.name if other else "Unknown",
            "messages": messages,
        }
    )

@router.post("/dm/{thread_id}/send")
def dm_send(thread_id: int, request: Request, content: str = Form(...), db: Session = Depends(get_db)):
    user_id, active = require_active_persona(request, db)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    if not active:
        return RedirectResponse(url="/chats", status_code=303)

    thread = db.query(models.DMThread).filter(models.DMThread.id == thread_id).first()
    if not thread or active.id not in (thread.persona_a_id, thread.persona_b_id):
        return RedirectResponse(url="/dm", status_code=303)

    text = content.strip()
    if not text:
        return RedirectResponse(url=f"/dm/{thread_id}", status_code=303)
    if len(text) > 500:
        text = text[:500]

    msg = models.DMMessage(
        thread_id=thread.id,
        sender_persona_id=active.id,
        content=text
    )
    db.add(msg)
    db.commit()

    return RedirectResponse(url=f"/dm/{thread_id}", status_code=303)


@router.get("/dm/{thread_id}/messages")
def dm_messages(thread_id: int, request: Request, after_id: int = 0, db: Session = Depends(get_db)):
    user_id, active = require_active_persona(request, db)
    if not user_id:
        return JSONResponse({"error": "not_logged_in"}, status_code=401)
    if not active:
        return JSONResponse({"error": "no_active_persona"}, status_code=403)

    thread = db.query(models.DMThread).filter(models.DMThread.id == thread_id).first()
    if not thread or active.id not in (thread.persona_a_id, thread.persona_b_id):
        return JSONResponse({"error": "not_allowed"}, status_code=403)

    rows = (
        db.query(models.DMMessage, models.Persona.name)
        .join(models.Persona, models.Persona.id == models.DMMessage.sender_persona_id)
        .filter(models.DMMessage.thread_id == thread.id)
        .filter(models.DMMessage.id > after_id)
        .order_by(models.DMMessage.id.asc())
        .limit(100)
        .all()
    )

    payload = [{
        "id": m.id,
        "sender_name": sender_name,
        "content": m.content,
        "created_at": m.created_at.isoformat(timespec="seconds"),
        "is_me": (m.sender_persona_id == active.id),
    } for m, sender_name in rows]

    return JSONResponse(payload)
