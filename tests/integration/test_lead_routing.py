from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.storage.models import LeadMessage


def test_lead_direct_answer_does_not_create_project(client: TestClient) -> None:
    before = client.get("/api/projects").json()
    decision = client.post(
        "/api/lead/messages",
        json={"message": "What can this version build?", "model": "mock"},
    )
    assert decision.status_code == 200
    assert decision.json()["route"] == "direct"
    assert client.get("/api/projects").json() == before


def test_lead_team_route_is_persisted_before_build(client: TestClient) -> None:
    decision = client.post(
        "/api/lead/messages",
        json={"message": "Build a product catalog for lamps", "model": "mock"},
    )
    assert decision.status_code == 200
    assert decision.json()["route"] == "team"
    with client.app.state.testing_session() as db:
        message = db.scalar(
            select(LeadMessage).where(LeadMessage.id == decision.json()["message_id"])
        )
        assert message is not None
        assert message.route == "team"
        assert message.request_count == 1
