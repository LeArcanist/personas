import uuid
from models import Persona


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


def test_create_persona_requires_login(client):
    r = client.post(
        "/personas/new",
        data={
            "category": "gaming",
            "name": "AnonPersona",
            "description": "",
            "is_public": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/login"


def test_create_persona_success(client, db_session):
    register_and_login(client, "alice", "alice@example.com")

    r = create_persona(client, "gaming", "AliceGaming", "My gaming persona", "1")
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/dashboard"

    persona = db_session.query(Persona).filter(Persona.name == "AliceGaming").first()
    assert persona is not None
    assert persona.category == "gaming"
    assert persona.description == "My gaming persona"
    assert persona.is_public is True


def test_create_persona_duplicate_name_blocked_for_same_user(client, db_session):
    register_and_login(client, "alice", "alice@example.com")

    r1 = create_persona(client, "gaming", "SameName", is_public="1")
    assert r1.status_code in (302, 303)

    r2 = create_persona(client, "academic", "SameName", is_public="0")
    assert r2.status_code == 200
    assert "already have a profile with that name" in r2.text

    personas = db_session.query(Persona).filter(Persona.name == "SameName").all()
    assert len(personas) == 1


def test_edit_persona_requires_owner(db_session, client_factory):
    client_a = client_factory()
    client_b = client_factory()

    register_and_login(client_a)
    register_and_login(client_b)

    persona_name = uniq("AliceGaming")
    create_persona(client_a, "gaming", persona_name, is_public="1")

    persona = db_session.query(Persona).filter(Persona.name == persona_name).first()
    assert persona is not None

    r = client_b.get(f"/personas/{persona.id}/edit", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/dashboard"


def test_edit_persona_save_updates_fields(client, db_session):
    register_and_login(client, "alice", "alice@example.com")
    create_persona(client, "gaming", "OldName", "Old desc", "0")

    persona = db_session.query(Persona).filter(Persona.name == "OldName").first()
    assert persona is not None

    r = client.post(
        f"/personas/{persona.id}/edit",
        data={
            "category": "professional",
            "name": "NewName",
            "description": "Updated desc",
            "is_public": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/dashboard"

    db_session.refresh(persona)
    assert persona.category == "professional"
    assert persona.name == "NewName"
    assert persona.description == "Updated desc"
    assert persona.is_public is True