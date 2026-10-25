from app.auth.dependencies import SESSION_COOKIE


def test_login_me_logout_and_cookie_flags(client):
    assert client.get("/api/auth/me").status_code == 200

    client.cookies.set(SESSION_COOKIE, "invalid-token")
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").json()["error"]["code"] == "authentication_required"

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "agentflow-admin"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "admin"
    assert "httponly" in login.headers["set-cookie"].lower()
    assert "samesite=lax" in login.headers["set-cookie"].lower()
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, login.json()["token"])

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_login_is_audited(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    audit = client.get("/api/audit-logs", params={"action": "auth.login_failed"})
    assert audit.status_code == 200
    assert audit.json()["total"] >= 1


def test_cookie_origin_is_checked_for_writes(client):
    response = client.post(
        "/api/flows",
        headers={"Origin": "https://evil.example"},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_origin_rejected"


def test_cookie_writes_require_origin(client):
    client.headers.pop("Origin", None)

    response = client.post("/api/flows", json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_origin_required"
