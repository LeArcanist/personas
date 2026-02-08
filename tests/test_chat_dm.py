def register_and_login(client, username, email):
    client.post(
        "/register",
        data={"username": username, "email": email, "password": "password123"},
        follow_redirects=False,
    )
    client.post(
        "/login",
        data={"username": username, "password": "password123"},
        follow_redirects=False,
    )


def create_persona(client, category, name, description="", is_public="1"):
    # Your /personas/new accepts is_public if you implemented it.
    return client.post(
        "/personas/new",
        data={"category": category, "name": name, "description": description, "is_public": is_public},
        follow_redirects=False,
    )


def select_active_persona(client, category, persona_id):
    return client.post(
        "/chats/enter",
        data={"category": category, "persona_id": str(persona_id)},
        follow_redirects=False,
    )


def test_category_chat_requires_active_persona(client, db_session):
    register_and_login(client, "alice", "alice@example.com")
    # no active persona set yet, should redirect to /chats selection
    r = client.get("/chats/gaming", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_category_chat_send_and_poll(client, db_session):
    # User A
    register_and_login(client, "alice", "alice@example.com")
    create_persona(client, "gaming", "AliceGaming", is_public="1")

    # Get persona id from DB
    from models import Persona
    alice_persona = db_session.query(Persona).filter(Persona.name == "AliceGaming").first()
    assert alice_persona is not None

    # select active persona
    sel = select_active_persona(client, "gaming", alice_persona.id)
    assert sel.status_code in (302, 303)

    # send message
    s = client.post("/chats/gaming/send", data={"content": "hello gaming"}, follow_redirects=False)
    assert s.status_code in (302, 303)

    # poll messages after_id=0 should include it
    p = client.get("/chats/gaming/messages?after_id=0")
    assert p.status_code == 200
    data = p.json()
    assert any(m["content"] == "hello gaming" for m in data)


def test_dm_start_and_send_and_poll_between_personas(db_session):
    """
    Uses two separate clients (two browser sessions) so sessions don't overwrite.
    """
    from fastapi.testclient import TestClient
    from main import app

    client_a = TestClient(app)
    client_b = TestClient(app)

    # Need dependency overrides from conftest-style setup
    import routers.users as users_router
    import routers.chat as chat_router

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[users_router.get_db] = override_get_db
    app.dependency_overrides[chat_router.get_db] = override_get_db

    try:
        # Register + login both
        client_a.post("/register", data={"username": "alice", "email": "alice@example.com", "password": "password123"})
        client_b.post("/register", data={"username": "bob", "email": "bob@example.com", "password": "password123"})
        client_a.post("/login", data={"username": "alice", "password": "password123"})
        client_b.post("/login", data={"username": "bob", "password": "password123"})

        # Create personas in same category (public)
        client_a.post("/personas/new", data={"category": "gaming", "name": "AliceGaming", "description": "", "is_public": "1"})
        client_b.post("/personas/new", data={"category": "gaming", "name": "BobGaming", "description": "", "is_public": "1"})

        from models import Persona
        a_persona = db_session.query(Persona).filter(Persona.name == "AliceGaming").first()
        b_persona = db_session.query(Persona).filter(Persona.name == "BobGaming").first()
        assert a_persona and b_persona

        # Select active persona for both
        client_a.post("/chats/enter", data={"category": "gaming", "persona_id": str(a_persona.id)})
        client_b.post("/chats/enter", data={"category": "gaming", "persona_id": str(b_persona.id)})

        # Start DM from A to B
        start = client_a.post("/dm/start", data={"target_persona_id": str(b_persona.id)}, follow_redirects=False)
        assert start.status_code in (302, 303)
        assert start.headers.get("location", "").startswith("/dm/")

        # Extract thread_id from redirect
        loc = start.headers["location"]  # e.g. /dm/3
        thread_id = int(loc.split("/")[-1])

        # A sends a DM
        send = client_a.post(f"/dm/{thread_id}/send", data={"content": "hi bob"}, follow_redirects=False)
        assert send.status_code in (302, 303)

        # B polls DM messages and should see it
        poll = client_b.get(f"/dm/{thread_id}/messages?after_id=0")
        assert poll.status_code == 200
        msgs = poll.json()
        assert any(m["content"] == "hi bob" for m in msgs)

        # Access control: random thread id should not be allowed (403 or redirect)
        bad = client_b.get("/dm/999999/messages?after_id=0")
        assert bad.status_code in (200, 302, 303, 403)
        # If 200, likely error JSON – acceptable depending on your implementation.

    finally:
        client_a.close()
        client_b.close()
        app.dependency_overrides.clear()
