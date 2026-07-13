from another_atom.agent.provider import MockLLMProvider
from another_atom.build.renderer import normalize_architecture_visual_tokens, validate_app_spec
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


def test_architecture_visual_tokens_are_normalized_before_engineering() -> None:
    _, architecture, _ = build_contracts()
    inaccessible = architecture.model_copy(
        update={
            "primary_color": "#00A000",
            "accent_color": "#000080",
            "background_color": "#C0C0C0",
        }
    )
    normalized = normalize_architecture_visual_tokens(inaccessible)

    assert normalized.background_color == "#C0C0C0"
    assert normalized.primary_color != inaccessible.primary_color
    _, _, app_spec = build_contracts()
    aligned = app_spec.model_copy(
        update={
            "primary_color": normalized.primary_color.lower(),
            "accent_color": normalized.accent_color.lower(),
            "background_color": normalized.background_color.lower(),
        }
    )
    report = validate_app_spec(aligned, architecture_spec=normalized)
    assert report.passed is True


def test_generic_web_code_passes_offline_sandbox_validation() -> None:
    provider = MockLLMProvider()
    prompt = "给我一个网页版扫雷游戏"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt)

    report = validate_app_spec(
        app_spec,
        prompt,
        blueprint=blueprint,
        architecture_spec=architecture,
    )

    assert report.passed is True
    assert {check.check_id for check in report.checks} >= {
        "web-source",
        "sandbox-boundary",
        "blueprint-pages",
    }


def test_single_screen_label_does_not_create_a_false_missing_page() -> None:
    provider = MockLLMProvider()
    prompt = "给我一个网页版扫雷游戏"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM).model_copy(
        update={"pages": ["index.html"]}
    )
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt)

    report = validate_app_spec(
        app_spec,
        prompt,
        blueprint=blueprint,
        architecture_spec=architecture,
    )
    page_check = next(check for check in report.checks if check.check_id == "blueprint-pages")

    assert page_check.status == "pass"
    assert report.passed is True


def test_generic_web_code_rejects_network_calls() -> None:
    provider = MockLLMProvider()
    prompt = "给我一个网页版扫雷游戏"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt).model_copy(
        update={"javascript": "fetch('https://example.com/state')"}
    )

    report = validate_app_spec(app_spec, blueprint=blueprint, architecture_spec=architecture)
    boundary = next(check for check in report.checks if check.check_id == "sandbox-boundary")
    assert report.passed is False
    assert boundary.status == "fail"
