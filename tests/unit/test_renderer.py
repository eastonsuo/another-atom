from another_atom.agent.provider import MockLLMProvider
from another_atom.build.renderer import validate_app_spec
from another_atom.contracts.schemas import Mode


def build_spec():
    provider = MockLLMProvider()
    blueprint = provider.create_blueprint("Build a lamp catalog", Mode.TEAM)
    visual = provider.create_visual_spec(blueprint)
    return provider.create_app_spec(blueprint, visual, "Build a lamp catalog")


def test_valid_app_spec_passes_deterministic_checks() -> None:
    report = validate_app_spec(build_spec())
    assert report.passed is True
    assert all(check.status == "pass" for check in report.checks)


def test_controlled_build_failure_is_reported() -> None:
    report = validate_app_spec(build_spec(), "[fail:build]")
    assert report.passed is False
    assert report.checks[-1].root_cause == "renderer"
    assert report.checks[-1].resolvable is True
