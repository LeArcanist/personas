from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter(prefix="/api", tags=["api"])


def is_persona_verified(db: Session, persona_id: int) -> bool:
    return (
        db.query(models.ExternalIdentity)
        .filter(models.ExternalIdentity.persona_id == persona_id)
        .first()
        is not None
    )


def serialize_persona(db: Session, persona: models.Persona) -> dict:
    return {
        "id": persona.id,
        "name": persona.name,
        "category": persona.category,
        "description": persona.description,
        "is_public": bool(persona.is_public),
        "is_verified": is_persona_verified(db, persona.id),
    }


@router.get("/personas/public")
def list_public_personas(category: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Persona).filter(models.Persona.is_public == True)

    if category:
        query = query.filter(models.Persona.category == category)

    personas = query.order_by(models.Persona.name.asc()).all()

    return [serialize_persona(db, p) for p in personas]


@router.get("/personas/public/{persona_id}")
def get_public_persona(persona_id: int, db: Session = Depends(get_db)):
    persona = (
        db.query(models.Persona)
        .filter(models.Persona.id == persona_id)
        .filter(models.Persona.is_public == True)
        .first()
    )

    if not persona:
        raise HTTPException(status_code=404, detail="Public persona not found")

    return serialize_persona(db, persona)


@router.get("/personas/public/{persona_id}/connections")
def get_public_persona_connections(persona_id: int, db: Session = Depends(get_db)):
    persona = (
        db.query(models.Persona)
        .filter(models.Persona.id == persona_id)
        .filter(models.Persona.is_public == True)
        .first()
    )

    if not persona:
        raise HTTPException(status_code=404, detail="Public persona not found")

    # Following
    following = (
        db.query(models.Persona)
        .join(
            models.PersonaFollow,
            models.PersonaFollow.following_persona_id == models.Persona.id
        )
        .filter(models.PersonaFollow.follower_persona_id == persona.id)
        .filter(models.Persona.is_public == True)
        .all()
    )

    # Followers
    followers = (
        db.query(models.Persona)
        .join(
            models.PersonaFollow,
            models.PersonaFollow.follower_persona_id == models.Persona.id
        )
        .filter(models.PersonaFollow.following_persona_id == persona.id)
        .filter(models.Persona.is_public == True)
        .all()
    )

    following_ids = {p.id for p in following}
    follower_ids = {p.id for p in followers}
    connection_ids = following_ids.intersection(follower_ids)

    connections = (
        db.query(models.Persona)
        .filter(models.Persona.id.in_(connection_ids))
        .filter(models.Persona.is_public == True)
        .all()
        if connection_ids else []
    )

    return {
        "persona_id": persona.id,
        "connections_count": len(connections),
        "connections": [serialize_persona(db, p) for p in connections],
    }


@router.get("/personas/{persona_id}/verification-status")
def get_persona_verification_status(persona_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    if persona.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    identities = (
        db.query(models.ExternalIdentity)
        .filter(models.ExternalIdentity.persona_id == persona.id)
        .all()
    )

    return {
        "persona_id": persona.id,
        "is_verified": len(identities) > 0,
        "linked_identities": [
            {
                "id": i.id,
                "provider": i.provider,
                "email": i.email,
                "name": i.name,
                "picture": i.picture,
            }
            for i in identities
        ]
    }


@router.get("/notifications")
def get_notifications(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    notifications = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .order_by(models.Notification.id.desc())
        .limit(50)
        .all()
    )

    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "link": n.link,
            "is_read": bool(n.is_read),
            "created_at": n.created_at.isoformat(timespec="seconds"),
        }
        for n in notifications
    ]


@router.get("/dm/threads")
def get_dm_threads(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    personas = (
        db.query(models.Persona)
        .filter(models.Persona.user_id == user_id)
        .all()
    )
    persona_ids = [p.id for p in personas]

    if not persona_ids:
        return []

    threads = (
        db.query(models.DMThread)
        .filter(
            (models.DMThread.persona_a_id.in_(persona_ids)) |
            (models.DMThread.persona_b_id.in_(persona_ids))
        )
        .order_by(models.DMThread.id.desc())
        .all()
    )

    payload = []

    for t in threads:
        if t.persona_a_id in persona_ids:
            my_persona_id = t.persona_a_id
            other_id = t.persona_b_id
        else:
            my_persona_id = t.persona_b_id
            other_id = t.persona_a_id

        my_persona = db.query(models.Persona).filter(models.Persona.id == my_persona_id).first()
        other = db.query(models.Persona).filter(models.Persona.id == other_id).first()

        last_message = (
            db.query(models.DMMessage)
            .filter(models.DMMessage.thread_id == t.id)
            .order_by(models.DMMessage.id.desc())
            .first()
        )

        payload.append({
            "thread_id": t.id,
            "category": t.category,
            "my_persona": {
                "id": my_persona.id,
                "name": my_persona.name,
            } if my_persona else None,
            "other_persona": {
                "id": other.id,
                "name": other.name,
                "is_verified": is_persona_verified(db, other.id),
            } if other else None,
            "last_message": {
                "id": last_message.id,
                "content": last_message.content,
                "created_at": last_message.created_at.isoformat(timespec="seconds"),
                "sender_persona_id": last_message.sender_persona_id,
            } if last_message else None
        })

    return payload

@router.get("/personas/me")
def get_my_personas(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    personas = (
        db.query(models.Persona)
        .filter(models.Persona.user_id == user_id)
        .order_by(models.Persona.name.asc())
        .all()
    )

    return [serialize_persona(db, p) for p in personas]


@router.get("/personas/{persona_id}/followers")
def get_persona_followers(persona_id: int, db: Session = Depends(get_db)):
    persona = (
        db.query(models.Persona)
        .filter(models.Persona.id == persona_id)
        .first()
    )

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    # Only expose followers publicly if the persona itself is public
    if not persona.is_public:
        raise HTTPException(status_code=403, detail="Persona is private")

    followers = (
        db.query(models.Persona)
        .join(
            models.PersonaFollow,
            models.PersonaFollow.follower_persona_id == models.Persona.id
        )
        .filter(models.PersonaFollow.following_persona_id == persona.id)
        .filter(models.Persona.is_public == True)
        .order_by(models.Persona.name.asc())
        .all()
    )

    return {
        "persona_id": persona.id,
        "followers_count": len(followers),
        "followers": [serialize_persona(db, p) for p in followers],
    }


@router.get("/personas/{persona_id}/following")
def get_persona_following(persona_id: int, db: Session = Depends(get_db)):
    persona = (
        db.query(models.Persona)
        .filter(models.Persona.id == persona_id)
        .first()
    )

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    # Only expose following publicly if the persona itself is public
    if not persona.is_public:
        raise HTTPException(status_code=403, detail="Persona is private")

    following = (
        db.query(models.Persona)
        .join(
            models.PersonaFollow,
            models.PersonaFollow.following_persona_id == models.Persona.id
        )
        .filter(models.PersonaFollow.follower_persona_id == persona.id)
        .filter(models.Persona.is_public == True)
        .order_by(models.Persona.name.asc())
        .all()
    )

    return {
        "persona_id": persona.id,
        "following_count": len(following),
        "following": [serialize_persona(db, p) for p in following],
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    notification = (
        db.query(models.Notification)
        .filter(models.Notification.id == notification_id)
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notification.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    notification.is_read = True
    db.commit()

    return {
        "success": True,
        "notification_id": notification.id,
        "is_read": notification.is_read,
    }