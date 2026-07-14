from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.storage.models import LeadMessage, User


def test_lead_direct_answer_does_not_create_project(client: TestClient) -> None:
    before = client.get("/api/projects").json()
    decision = client.post(
        "/api/lead/messages",
        json={"message": "What can this version build?", "model": "mock"},
    )
    assert decision.status_code == 200
    assert decision.json()["route"] == "direct"
    assert client.get("/api/projects").json() == before


def test_lead_structured_clarification_does_not_create_project(
    client: TestClient,
) -> None:
    before = client.get("/api/projects").json()
    decision = client.post(
        "/api/lead/messages",
        json={"message": "我想要实现一个翻译功能", "model": "mock"},
    )

    assert decision.status_code == 200
    payload = decision.json()
    assert payload["route"] == "clarify"
    assert len(payload["clarification_questions"]) == 2
    assert all(len(question["options"]) >= 2 for question in payload["clarification_questions"])
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


def test_lead_llm_failure_settles_observed_call_and_releases_rest(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/lead/messages",
        json={"message": "Build a catalog [fail:llm]", "model": "mock"},
    )
    assert response.status_code == 502
    assert response.json()["code"] == "LEAD_FAILED"
    quota = client.get("/api/quota").json()
    assert quota["used"] == 1
    assert quota["reserved"] == 0


def test_lead_platform_failure_does_not_leave_reserved_quota(client: TestClient) -> None:
    response = client.post(
        "/api/lead/messages",
        json={"message": "Build a catalog [fail:platform]", "model": "mock"},
    )
    assert response.status_code == 502
    assert response.json()["code"] == "LEAD_PLATFORM_FAILED"
    quota = client.get("/api/quota").json()
    assert quota["used"] == 1
    assert quota["reserved"] == 0


def test_lead_usage_is_recorded_without_enforcing_the_configured_limit(
    client: TestClient,
) -> None:
    assert client.get("/api/quota").status_code == 200
    with client.app.state.testing_session() as db:
        user = db.get(User, "demo-user")
        assert user is not None
        user.quota_limit = 0
        db.commit()

    response = client.post(
        "/api/lead/messages",
        json={"message": "What can this version build?", "model": "mock"},
    )

    assert response.status_code == 200
    quota = client.get("/api/quota").json()
    assert quota["limit"] == 0
    assert quota["used"] == 1
    assert quota["reserved"] == 0
