import pytest
from pydantic import ValidationError

from another_atom.contracts.schemas import Blueprint, RunCreate, SupportLevel


def test_prompt_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        RunCreate(prompt="   ")


def test_blueprint_rejects_routes_outside_v1_scope() -> None:
    with pytest.raises(ValidationError, match="Home, Catalog, and Product"):
        Blueprint(
            project_name="Bad scope",
            support_level=SupportLevel.SUPPORTED,
            pages=["Dashboard"],
            modules=["Charts"],
            visual_direction="Dense dashboard",
        )


def test_blueprint_accepts_controlled_catalog_pages() -> None:
    blueprint = Blueprint(
        project_name="Mono Market",
        support_level=SupportLevel.SUPPORTED,
        pages=["Home", "Catalog", "Product"],
        modules=["Hero", "Grid"],
        visual_direction="Editorial",
    )
    assert blueprint.capability_policy_version == "catalog-v1"
