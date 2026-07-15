import base64

from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.agent.provider import LLMProviderError, MockLLMProvider
from another_atom.storage.models import Artifact, ImageContext, ReferenceAttachment

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def _upload_image(client: TestClient) -> dict:
    response = client.post(
        "/api/attachments",
        files={"file": ("reference.png", PNG_1X1, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_image_upload_uses_server_detected_metadata_and_authenticated_content(
    client: TestClient,
) -> None:
    attachment = _upload_image(client)

    assert attachment["media_type"] == "image/png"
    assert attachment["width"] == 1
    assert attachment["height"] == 1
    assert attachment["status"] == "ready"
    assert attachment["content_hash"].startswith("sha256:")
    content = client.get(attachment["content_url"])
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/png")
    assert content.content == PNG_1X1


def test_upload_rejects_a_file_that_only_claims_to_be_an_image(client: TestClient) -> None:
    response = client.post(
        "/api/attachments",
        files={"file": ("fake.png", b"not an image", "image/png")},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ATTACHMENT_TYPE_UNSUPPORTED"


def test_team_run_reuses_the_lead_image_context(client: TestClient) -> None:
    attachment = _upload_image(client)
    decision = client.post(
        "/api/lead/messages",
        json={
            "message": "Build a small gallery using this screenshot as a visual reference",
            "model": "mock",
            "attachment_ids": [attachment["id"]],
        },
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["route"] == "team"

    created = client.post(
        "/api/runs",
        json={
            "prompt": "Build a small gallery using this screenshot as a visual reference",
            "mode": "team",
            "model": "mock",
            "attachment_ids": [attachment["id"]],
            "lead_message_id": decision.json()["message_id"],
        },
    )
    assert created.status_code == 201, created.text

    with client.app.state.testing_session() as db:
        stored = db.get(ReferenceAttachment, attachment["id"])
        assert stored is not None
        assert stored.status == "analyzed"
        assert stored.project_id == created.json()["project_id"]
        image_context = db.scalar(
            select(ImageContext).where(
                ImageContext.lead_message_id == decision.json()["message_id"]
            )
        )
        assert image_context is not None
        assert image_context.run_id == created.json()["run_id"]
        artifact = db.scalar(
            select(Artifact).where(
                Artifact.run_id == created.json()["run_id"],
                Artifact.artifact_type == "image_context",
            )
        )
        assert artifact is not None
        assert artifact.payload["image_context_id"] == image_context.id


def test_unsent_attachment_can_be_deleted(client: TestClient) -> None:
    attachment = _upload_image(client)

    response = client.delete(f"/api/attachments/{attachment['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/attachments/{attachment['id']}").status_code == 404


def test_project_change_message_carries_image_context_into_the_approved_run(
    client: TestClient,
) -> None:
    initial = client.post(
        "/api/runs",
        json={"prompt": "Build a simple product card", "mode": "team", "model": "mock"},
    ).json()
    current = client.get(f"/api/runs/{initial['run_id']}").json()
    if current["status"] == "awaiting_approval":
        current = client.post(
            f"/api/runs/{initial['run_id']}/approve",
            json={"blueprint": current["blueprint"]},
        ).json()
    attachment = _upload_image(client)

    proposal = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={
            "message": "Update the product card to follow this visual reference",
            "model": "mock",
            "attachment_ids": [attachment["id"]],
        },
    )
    assert proposal.status_code == 200, proposal.text
    payload = proposal.json()
    assert payload["intent"] == "propose_change"
    assert payload["user_message"]["payload"]["attachments"][0]["id"] == attachment["id"]
    assert (
        payload["user_message"]["payload"]["image_context"]["observations"][0]["attachment_id"]
        == attachment["id"]
    )

    approved = client.post(
        f"/api/projects/{initial['project_id']}/change-proposals/{payload['proposal_id']}/approve"
    )
    assert approved.status_code == 202, approved.text
    with client.app.state.testing_session() as db:
        artifact = db.scalar(
            select(Artifact).where(
                Artifact.run_id == approved.json()["run_id"],
                Artifact.artifact_type == "image_context",
            )
        )
        assert artifact is not None


def test_project_image_message_retry_reuses_the_persisted_user_turn(
    client: TestClient,
    monkeypatch,
) -> None:
    initial = client.post(
        "/api/runs",
        json={"prompt": "Build a simple product card", "mode": "team", "model": "mock"},
    ).json()
    current = client.get(f"/api/runs/{initial['run_id']}").json()
    if current["status"] == "awaiting_approval":
        client.post(
            f"/api/runs/{initial['run_id']}/approve",
            json={"blueprint": current["blueprint"]},
        )
    attachment = _upload_image(client)

    class FlakyVisionProvider(MockLLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.vision_attempts = 0

        def analyze_images(self, images):
            self.vision_attempts += 1
            if self.vision_attempts == 1:
                raise LLMProviderError("vision temporarily unavailable")
            return super().analyze_images(images)

    provider = FlakyVisionProvider()
    monkeypatch.setattr(
        "another_atom.api.routes.get_llm_provider",
        lambda model=None: provider,
    )
    payload = {
        "message": "Update this page to match the screenshot",
        "model": "mock",
        "client_message_id": "optimistic-stable-image-turn",
        "attachment_ids": [attachment["id"]],
    }

    failed = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json=payload,
    )
    assert failed.status_code == 502, failed.text
    assert failed.json()["code"] == "VISION_MODEL_UNAVAILABLE"
    after_failure = client.get(f"/api/projects/{initial['project_id']}/messages").json()
    failed_users = [
        message
        for message in after_failure
        if message["payload"].get("client_message_id") == payload["client_message_id"]
    ]
    assert len(failed_users) == 1
    failed_leads = [message for message in after_failure if message["role"] == "lead"]
    assert any(
        message["message_type"] == "error"
        and message["payload"].get("error_code") == "VISION_MODEL_UNAVAILABLE"
        for message in failed_leads
    )

    succeeded = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json=payload,
    )
    assert succeeded.status_code == 200, succeeded.text
    repeated = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json=payload,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["user_message"]["id"] == succeeded.json()["user_message"]["id"]
    assert repeated.json()["lead_message"]["id"] == succeeded.json()["lead_message"]["id"]
    assert provider.vision_attempts == 2

    messages = client.get(f"/api/projects/{initial['project_id']}/messages").json()
    persisted_users = [
        message
        for message in messages
        if message["payload"].get("client_message_id") == payload["client_message_id"]
    ]
    assert len(persisted_users) == 1
