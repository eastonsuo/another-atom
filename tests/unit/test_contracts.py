from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from another_atom.api.routes import _coerce_review_report
from another_atom.contracts.schemas import (
    Blueprint,
    EventView,
    LeadDecision,
    LeadRoute,
    RunCreate,
    SupportLevel,
)


def test_event_view_normalizes_naive_database_timestamp_to_utc() -> None:
    event = EventView(
        event_id="1",
        sequence=1,
        run_id="run-1",
        type="agent.attempt.started",
        payload={},
        timestamp=datetime(2026, 7, 14, 15, 0, 0),
    )

    assert event.timestamp.tzinfo is UTC
    assert '"timestamp":"2026-07-14T15:00:00Z"' in event.model_dump_json()


def test_prompt_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        RunCreate(prompt="   ")


def test_blueprint_rejects_blank_web_screen_labels() -> None:
    with pytest.raises(ValidationError, match="cannot be blank"):
        Blueprint(
            project_name="Web tool",
            support_level=SupportLevel.SUPPORTED,
            pages=["Dashboard", "   "],
            modules=["Charts"],
            visual_direction="Dense dashboard",
        )


def test_blueprint_accepts_arbitrary_web_screens() -> None:
    blueprint = Blueprint(
        project_name="Mono Market",
        support_level=SupportLevel.SUPPORTED,
        product_type="web_game",
        pages=["Game"],
        modules=["Board", "Timer", "Restart"],
        visual_direction="Retro game",
    )
    assert blueprint.capability_policy_version == "web-v1"
    assert blueprint.product_type == "web_game"


def test_lead_clarify_requires_structured_questions() -> None:
    with pytest.raises(ValidationError, match="requires structured clarification"):
        LeadDecision(
            route=LeadRoute.CLARIFY,
            response="Please choose",
            reason="Material choices are missing",
        )


def test_lead_direct_rejects_clarification_questions() -> None:
    with pytest.raises(ValidationError, match="Only a clarify route"):
        LeadDecision(
            route=LeadRoute.DIRECT,
            response="Answer",
            reason="Question only",
            clarification_questions=[
                {
                    "id": "platform",
                    "question": "Which platform?",
                    "options": [
                        {"value": "web", "label": "Web"},
                        {"value": "mobile", "label": "Mobile"},
                    ],
                }
            ],
        )


def test_legacy_data_review_remains_readable_as_review_report() -> None:
    report = _coerce_review_report(
        {
            "summary": "Legacy data review",
            "data_checks": ["Catalog records are complete"],
            "engineering_checks": ["Validation passed"],
            "warnings": [],
            "suggested_actions": ["accept"],
        }
    )

    assert report is not None
    assert report.verdict == "accept"
    assert report.reviewer_mode == "deterministic_only"
    assert report.data_findings == ["Catalog records are complete"]
