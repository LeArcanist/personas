import uuid
from models import Persona, ExternalIdentity, Notification, User


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


def test_public_personas_returns_only_public(client, db_session):
    username, _ = register_and_login(client)

    public_name = uniq("PublicOne")
    private_name = uniq("PrivateOne")

    create_persona(client, "gaming", public_name, is_public="1")
    create_persona(client, "gaming", private_name, is_public="0")

    r = client.get("/api/personas/public")
    assert r.status_code == 200

    data = r.json()
    ids_by_name = {p["name"]: p["id"] for p in data}

    assert public_name in ids_by_name
    assert private_name not in ids_by_name


def test_public_personas_filter_by_category(client, db_session):
    register_and_login(client)

    game_name = uniq("GamePersona")
    work_name = uniq("WorkPersona")

    create_persona(client, "gaming", game_name, is_public="1")
    create_persona(client, "professional", work_name, is_public="1")

    r = client.get("/api/personas/public?category=gaming")
    assert r.status_code == 200

    data = r.json()
    names = [p["name"] for p in data]

    assert game_name in names
    assert work_name not in names


def test_get_public_persona_404_for_private(client, db_session):
    register_and_login(client)

    hidden_name = uniq("HiddenPersona")
    create_persona(client, "gaming", hidden_name, is_public="0")

    persona = (
        db_session.query(Persona)
        .filter(Persona.name == hidden_name)
        .order_by(Persona.id.desc())
        .first()
    )
    assert persona is not None
    assert persona.is_public is False

    r = client.get(f"/api/personas/public/{persona.id}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Public persona not found"


def test_get_my_personas_requires_login(client):
    r = client.get("/api/personas/me")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"


def test_get_my_personas_returns_logged_in_users_personas(client, db_session):
    username, _ = register_and_login(client)

    name1 = uniq("AliceGaming")
    name2 = uniq("AliceAcademic")

    create_persona(client, "gaming", name1, is_public="1")
    create_persona(client, "academic", name2, is_public="0")

    r = client.get("/api/personas/me")
    assert r.status_code == 200

    data = r.json()
    names = [p["name"] for p in data]

    assert name1 in names
    assert name2 in names


def test_verification_status_requires_login(client):
    r = client.get("/api/personas/1/verification-status")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"


def test_verification_status_returns_true_when_identity_exists(client, db_session):
    register_and_login(client, "alice", "alice@example.com")
    create_persona(client, "gaming", "VerifiedPersona", is_public="1")

    persona = db_session.query(Persona).filter(Persona.name == "VerifiedPersona").first()
    assert persona is not None

    identity = ExternalIdentity(
        persona_id=persona.id,
        provider="google",
        provider_user_id="google-123",
        email="alice@example.com",
        name="Alice",
        picture="https://example.com/pic.png",
    )
    db_session.add(identity)
    db_session.commit()

    r = client.get(f"/api/personas/{persona.id}/verification-status")
    assert r.status_code == 200

    data = r.json()
    assert data["persona_id"] == persona.id
    assert data["is_verified"] is True
    assert len(data["linked_identities"]) == 1
    assert data["linked_identities"][0]["provider"] == "google"


def test_notifications_requires_login(client):
    r = client.get("/api/notifications")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"


def test_notifications_returns_users_notifications(client, db_session):
    username, _ = register_and_login(client)

    user = db_session.query(User).filter(User.username == username).first()
    assert user is not None

    older_title = uniq("Older")
    newer_title = uniq("Newer")

    n1 = Notification(
        user_id=user.id,
        type="test",
        title=older_title,
        message="Old message",
        link="/older",
        is_read=False,
    )
    n2 = Notification(
        user_id=user.id,
        type="test",
        title=newer_title,
        message="New message",
        link="/newer",
        is_read=True,
    )
    db_session.add_all([n1, n2])
    db_session.commit()

    r = client.get("/api/notifications")
    assert r.status_code == 200

    data = r.json()
    titles = [n["title"] for n in data]

    assert older_title in titles
    assert newer_title in titles

def test_mark_notification_read_success(client, db_session):
    username, _ = register_and_login(client)

    user = db_session.query(User).filter(User.username == username).first()
    assert user is not None

    title = uniq("ReadMe")

    notif = Notification(
        user_id=user.id,
        type="test",
        title=title,
        message="hello",
        link="/x",
        is_read=False,
    )
    db_session.add(notif)
    db_session.commit()
    db_session.refresh(notif)

    r = client.post(f"/api/notifications/{notif.id}/read")
    assert r.status_code == 200

    data = r.json()
    assert data["success"] is True
    assert data["notification_id"] == notif.id
    assert data["is_read"] is True

    db_session.refresh(notif)
    assert notif.is_read is True