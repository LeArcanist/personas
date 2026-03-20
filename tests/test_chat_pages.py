import uuid
from fastapi.testclient import TestClient
from main import app
from models import Persona, DMThread


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


def test_chats_home_requires_login(client):
    r = client.get("/chats", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/login"


def test_category_chat_requires_active_persona(client, db_session):
    register_and_login(client, "alice", "alice@example.com")

    r = client.get("/chats/gaming", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/chats"


def test_category_chat_page_loads_with_active_persona(client, db_session):
    register_and_login(client, "alice", "alice@example.com")
    create_persona(client, "gaming", "AliceGaming", is_public="1")

    persona = db_session.query(Persona).filter(Persona.name == "AliceGaming").first()
    assert persona is not None

    select_active_persona(client, "gaming", persona.id)

    r = client.get("/chats/gaming", follow_redirects=False)
    assert r.status_code == 200
    assert "AliceGaming" in r.text


def test_dm_start_creates_thread(db_session, client_factory):
    client_a = client_factory()
    client_b = client_factory()

    user_a, email_a = register_and_login(client_a)
    user_b, email_b = register_and_login(client_b)

    persona_a_name = uniq("AliceGaming")
    persona_b_name = uniq("BobGaming")

    create_persona(client_a, "gaming", persona_a_name, is_public="1")
    create_persona(client_b, "gaming", persona_b_name, is_public="1")

    alice = db_session.query(Persona).filter(Persona.name == persona_a_name).first()
    bob = db_session.query(Persona).filter(Persona.name == persona_b_name).first()
    assert alice and bob

    select_active_persona(client_a, "gaming", alice.id)

    r = client_a.post(
        "/dm/start",
        data={"target_persona_id": str(bob.id)},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers["location"].startswith("/dm/")

    thread = db_session.query(DMThread).filter(
        ((DMThread.persona_a_id == alice.id) & (DMThread.persona_b_id == bob.id)) |
        ((DMThread.persona_a_id == bob.id) & (DMThread.persona_b_id == alice.id))
    ).first()
    assert thread is not None


def test_dm_start_reuses_existing_thread(db_session, client_factory):
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

    existing = DMThread(
        persona_a_id=alice.id,
        persona_b_id=bob.id,
        category="gaming",
    )
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    select_active_persona(client_a, "gaming", alice.id)

    r = client_a.post(
        "/dm/start",
        data={"target_persona_id": str(bob.id)},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers["location"] == f"/dm/{existing.id}"