def test_register_redirects(client):
    r = client.post(
        "/register",
        data={"username": "alice", "email": "alice@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)


def test_login_sets_session_and_allows_dashboard(client):
    # register
    client.post(
        "/register",
        data={"username": "bob", "email": "bob@example.com", "password": "password123"},
        follow_redirects=False,
    )

    # login
    r = client.post(
        "/login",
        data={"username": "bob", "password": "password123"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    # dashboard should be accessible (session cookie maintained by TestClient)
    d = client.get("/dashboard", follow_redirects=False)
    assert d.status_code == 200


def test_dashboard_requires_login(client):
    # new client session (no login)
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (302, 303)
