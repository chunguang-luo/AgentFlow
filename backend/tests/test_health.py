def test_liveness_and_readiness(client):
    liveness = client.get("/healthz")
    assert liveness.status_code == 200
    assert liveness.json()["status"] == "ok"

    readiness = client.get("/readyz")
    assert readiness.status_code == 200
    assert readiness.json()["database"] == {"status": "ok", "engine": "sqlite"}


def test_frontend_health_alias(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["service"] == "AgentFlow"


def test_openapi_is_available(client):
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "AgentFlow API"
    assert "/api/health" in schema["paths"]
