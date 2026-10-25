def test_unknown_route_uses_error_contract(client):
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["X-Request-ID"]
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert body["request_id"] == response.headers["X-Request-ID"]
