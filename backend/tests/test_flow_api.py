import pytest

from app.auth.dependencies import SESSION_COOKIE
from app.auth.service import AuthService
from app.db.session import SessionLocal, get_engine


def definition(name: str = "API Flow") -> dict:
    return {
        "name": name,
        "description": "Created through API",
        "inputs": [],
        "steps": [
            {
                "id": "analyze",
                "name": "Analyze",
                "type": "agent",
                "config": {"prompt": "Analyze", "provider": "mock"},
            }
        ],
    }


def test_flow_validate_create_update_publish_versions_and_export(client):
    valid = client.post("/api/flows/validate", json=definition())
    assert valid.status_code == 200
    assert valid.json()["valid"] is True

    invalid = definition()
    invalid["steps"][0]["config"].pop("provider")
    rejected = client.post("/api/flows/validate", json=invalid)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "flow_validation_error"

    created = client.post("/api/flows", json=definition("First Flow"))
    assert created.status_code == 201
    flow = created.json()
    assert flow["status"] == "draft"
    assert flow["draft_definition"]["name"] == "First Flow"

    updated_definition = definition("First Flow Updated")
    updated = client.put(f"/api/flows/{flow['id']}", json=updated_definition)
    assert updated.status_code == 200
    assert updated.json()["draft_definition"]["name"] == "First Flow Updated"

    published = client.post(f"/api/flows/{flow['id']}/publish")
    assert published.status_code == 201
    assert published.json()["version"] == 1

    versions = client.get(f"/api/flows/{flow['id']}/versions")
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()] == [1]

    version_detail = client.get(f"/api/flows/{flow['id']}/versions/1")
    assert version_detail.status_code == 200
    assert version_detail.json()["definition"]["name"] == "First Flow Updated"

    exported = client.get(f"/api/flows/{flow['id']}/export", params={"version": 1})
    assert exported.status_code == 200
    assert exported.json()["name"] == "First Flow Updated"


def test_flow_import_and_pagination(client):
    imported = client.post("/api/flows/import", json=definition("Imported Flow"))
    assert imported.status_code == 201
    assert imported.json()["name"] == "Imported Flow"

    client.post("/api/flows", json=definition("Second Flow"))
    page = client.get(
        "/api/flows",
        params={"page": 1, "page_size": 1, "name": "flow", "sort": "name_asc"},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["page_size"] == 1
    assert len(page.json()["items"]) == 1


def test_run_creation_is_idempotent(client):
    flow_response = client.post("/api/flows", json=definition("Idempotent Flow"))
    flow_id = flow_response.json()["id"]
    client.post(f"/api/flows/{flow_id}/publish")

    first = client.post(
        "/api/runs",
        json={"flow_id": flow_id, "inputs": {}, "idempotency_key": "stable"},
    )
    second = client.post(
        "/api/runs",
        json={"flow_id": flow_id, "inputs": {}, "idempotency_key": "stable"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_viewer_cannot_write_flows_or_read_audit(client):
    SessionLocal.configure(bind=get_engine())
    with SessionLocal() as session:
        AuthService(session).create_user(
            username="viewer-user", password="viewer-password", role="viewer"
        )
        session.commit()

    login = client.post(
        "/api/auth/login",
        json={"username": "viewer-user", "password": "viewer-password"},
    )
    assert login.status_code == 200
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, login.json()["token"])

    assert client.get("/api/flows").status_code == 200
    denied = client.post("/api/flows", json=definition("Denied Flow"))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "permission_denied"
    assert client.post("/api/providers/mock/health-check").status_code == 403
    assert client.get("/api/audit-logs").status_code == 403


def test_flow_operations_are_audited(client):
    created = client.post("/api/flows", json=definition("Audited Flow"))
    flow_id = created.json()["id"]
    client.post(f"/api/flows/{flow_id}/publish")

    audit = client.get(
        "/api/audit-logs",
        params={"target_type": "flow", "page_size": 100},
    )
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["items"]}
    assert {"flow.created", "flow.published"} <= actions


@pytest.mark.parametrize(
    ("endpoint", "method"),
    [
        ("/api/flows", "get"),
        ("/api/runs", "get"),
        ("/api/providers", "get"),
    ],
)
def test_business_endpoints_require_authentication(client, endpoint, method):
    client.cookies.clear()
    response = getattr(client, method)(endpoint)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
