from another_atom.agent.provider import MockLLMProvider
from another_atom.build.renderer import validate_app_spec
from another_atom.contracts.schemas import Blueprint, Mode


def build_contracts():
    provider = MockLLMProvider()
    blueprint = provider.create_blueprint("Build a lamp catalog", Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, "Build a lamp catalog")
    return blueprint, architecture, app_spec


def build_spec():
    return build_contracts()[2]


def test_valid_app_spec_passes_deterministic_checks() -> None:
    report = validate_app_spec(build_spec())
    assert report.passed is True
    assert all(check.status == "pass" for check in report.checks)


def test_controlled_build_failure_is_reported() -> None:
    report = validate_app_spec(build_spec(), "[fail:build]")
    assert report.passed is False
    assert report.checks[-1].root_cause == "renderer"
    assert report.checks[-1].resolvable is True


def test_blueprint_page_contract_is_enforced() -> None:
    blueprint, architecture, app_spec = build_contracts()
    pages = [page.model_copy() for page in app_spec.pages]
    pages[-1] = pages[-1].model_copy(update={"route": "/catalog", "name": "Duplicate"})
    invalid = app_spec.model_copy(update={"pages": pages})
    report = validate_app_spec(
        invalid,
        blueprint=blueprint,
        architecture_spec=architecture,
    )
    assert report.passed is False
    page_check = next(check for check in report.checks if check.check_id == "blueprint-pages")
    assert page_check.status == "fail"
    assert "Product" in (page_check.detail or "")


def test_unknown_mapped_requirement_is_not_claimed_as_validated() -> None:
    blueprint, architecture, app_spec = build_contracts()
    blueprint = Blueprint.model_validate(
        blueprint.model_copy(update={"mapped_requirements": ["Real-time inventory sync"]})
    )
    report = validate_app_spec(
        app_spec,
        blueprint=blueprint,
        architecture_spec=architecture,
    )
    check = next(check for check in report.checks if check.check_id == "mapped-requirements")
    assert report.passed is False
    assert check.status == "fail"


def test_visual_tokens_require_contrast_and_architecture_alignment() -> None:
    blueprint, architecture, app_spec = build_contracts()
    invalid = app_spec.model_copy(update={"primary_color": app_spec.background_color})
    report = validate_app_spec(
        invalid,
        blueprint=blueprint,
        architecture_spec=architecture,
    )
    check = next(check for check in report.checks if check.check_id == "visual-tokens")
    assert report.passed is False
    assert check.status == "fail"
