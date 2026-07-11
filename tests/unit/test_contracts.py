import pytest
from pydantic import ValidationError

from another_atom.contracts.schemas import Blueprint, RunCreate, SupportLevel


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
