import uuid
from models import Persona, PersonaFollow, Notification


def uniq(prefix="test"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def register_and_login(client, username=None, email=None, password="password123"):
    if username is None:
        username = uniq("user")
    if email is None:
        email = f"{username}@example.com"

    client.post(
        "/register",
        data={"username": username, "email": email, "password": password},
        follow_redirects=False,
    )
    client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    return username, email


def create_persona(client, category, name, description="", is_public="1"):
    return client.post(
        "/personas/new",
        data={
            "category": category,
            "name": name,
            "description": description,
            "is_public": is_public,
        },
        follow_redirects=False,
    )


def select_active_persona(client, category, persona_id):
    return client.post(
        "/chats/enter",
        data={"category": category, "persona_id": str(persona_id)},
        follow_redirects=False,
    )


def test_follow_persona_creates_follow_and_notification(db_session, monkeypatch, client_factory):
    async def fake_send_to_user(user_id, payload):
        return None

    from routers.users import notification_manager
    monkeypatch.setattr(notification_manager, "send_to_user", fake_send_to_user)

    client_a = client_factory()
    client_b = client_factory()

    user_a, _ = register_and_login(client_a)
    user_b, _ = register_and_login(client_b)

    persona_a_name = uniq("AliceGaming")
    persona_b_name = uniq("BobGaming")

    create_persona(client_a, "gaming", persona_a_name, is_public="1")
    create_persona(client_b, "gaming", persona_b_name, is_public="1")

    alice = db_session.query(Persona).filter(Persona.name == persona_a_name).first()
    bob = db_session.query(Persona).filter(Persona.name == persona_b_name).first()
    assert alice and bob

    select_active_persona(client_a, "gaming", alice.id)

    r = client_a.post(f"/personas/{bob.id}/follow", follow_redirects=False)
    assert r.status_code in (302, 303)

    follow = (
        db_session.query(PersonaFollow)
        .filter(PersonaFollow.follower_persona_id == alice.id)
        .filter(PersonaFollow.following_persona_id == bob.id)
        .first()
    )
    assert follow is not None

    notif = (
        db_session.query(Notification)
        .filter(Notification.user_id == bob.user_id)
        .filter(Notification.type == "persona_follow")
        .first()
    )
    assert notif is not None


def test_unfollow_persona_removes_follow(db_session, client_factory):
    client_a = client_factory()
    client_b = client_factory()

    register_and_login(client_a)
    register_and_login(client_b)

    persona_a_name = uniq("AliceGaming")
    persona_b_name = uniq("BobGaming")

    create_persona(client_a, "gaming", persona_a_name, is_public="1")
    create_persona(client_b, "gaming", persona_b_name, is_public="1")

    alice = db_session.query(Persona).filter(Persona.name == persona_a_name).first()
    bob = db_session.query(Persona).filter(Persona.name == persona_b_name).first()
    assert alice and bob

    db_session.add(
        PersonaFollow(
            follower_persona_id=alice.id,
            following_persona_id=bob.id,
        )
    )
    db_session.commit()

    select_active_persona(client_a, "gaming", alice.id)

    r = client_a.post(f"/personas/{bob.id}/unfollow", follow_redirects=False)
    assert r.status_code in (302, 303)

    follow = (
        db_session.query(PersonaFollow)
        .filter(PersonaFollow.follower_persona_id == alice.id)
        .filter(PersonaFollow.following_persona_id == bob.id)
        .first()
    )
    assert follow is None